"""State Registry — 统一状态注册表

从所有状态系统读取，合并为统一视图。
检测并列状态机之间的分歧，提供报价历史追踪。

状态系统来源:
  - CRM SQLite (customers, messages, quotes, orders)
  - lead_state_engine 状态机 (9 states)
  - ai_overlay/stabilization.py StateSyncEngine (10 states)
  - ConversationLock (in-memory, process-local)
  - review_queue.json
  - followup_schedule.db
"""
import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger("glowforge.state_registry")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# lead_state_engine 状态 → StateSyncEngine 状态映射
LEAD_TO_SYNC_MAP = {
    "NEW": "NEW",
    "INTERESTED": "QUALIFYING",
    "REQUESTED_PRICE": "PRICING",
    "QUOTED": "PRICING",
    "NEGOTIATING": "NEGOTIATING",
    "HOT": "CLOSING",
    "COLD": "COLD",
    "CLOSED_WON": "CLOSED_WON",
    "CLOSED_LOST": "CLOSED_LOST",
}

# StateSyncEngine 状态 → lead_state_engine 状态映射（反向）
SYNC_TO_LEAD_MAP = {v: k for k, v in LEAD_TO_SYNC_MAP.items()}

# 动作/状态兼容性矩阵
# result: ALLOW | BLOCK | MODIFY
ACTION_STATE_MATRIX = {
    "send_intro": {
        "NEW": "ALLOW", "QUALIFYING": "BLOCK", "PRICING": "BLOCK",
        "NEGOTIATING": "BLOCK", "CLOSING": "BLOCK", "COLD": "BLOCK",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_followup": {
        "NEW": "BLOCK", "QUALIFYING": "ALLOW", "PRICING": "ALLOW",
        "NEGOTIATING": "BLOCK", "CLOSING": "BLOCK", "COLD": "ALLOW",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_quote": {
        "NEW": "BLOCK", "QUALIFYING": "ALLOW", "PRICING": "ALLOW",
        "NEGOTIATING": "MODIFY", "CLOSING": "MODIFY", "COLD": "BLOCK",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_negotiation": {
        "NEW": "BLOCK", "QUALIFYING": "BLOCK", "PRICING": "ALLOW",
        "NEGOTIATING": "ALLOW", "CLOSING": "ALLOW", "COLD": "BLOCK",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_confirmation": {
        "NEW": "BLOCK", "QUALIFYING": "BLOCK", "PRICING": "BLOCK",
        "NEGOTIATING": "ALLOW", "CLOSING": "ALLOW", "COLD": "BLOCK",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_catalog": {
        "NEW": "ALLOW", "QUALIFYING": "ALLOW", "PRICING": "MODIFY",
        "NEGOTIATING": "MODIFY", "CLOSING": "BLOCK", "COLD": "ALLOW",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
    "send_price_discussion": {
        "NEW": "BLOCK", "QUALIFYING": "BLOCK", "PRICING": "ALLOW",
        "NEGOTIATING": "ALLOW", "CLOSING": "MODIFY", "COLD": "BLOCK",
        "CLOSED_WON": "BLOCK", "CLOSED_LOST": "BLOCK",
    },
}

# intent → 动作类型映射
INTENT_TO_ACTION = {
    "询价": "send_quote",
    "比价": "send_negotiation",
    "问工艺": "send_catalog",
    "要样品": "send_quote",
    "问交期": "send_price_discussion",
    "下单": "send_confirmation",
    "售后": "send_followup",
    "合作": "send_intro",
    "要目录": "send_catalog",
    "跟进": "send_followup",
    "其他": "send_followup",
}

# 风险评分
ACTION_RISK = {
    "send_intro": "low",
    "send_followup": "low",
    "send_catalog": "low",
    "send_quote": "high",
    "send_negotiation": "high",
    "send_price_discussion": "medium",
    "send_confirmation": "critical",
}

_WAL_LOCK = threading.Lock()


class StateRegistry:
    """统一状态注册表 — 所有状态系统的唯一入口"""

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or BASE_DIR
        self.db_path = os.path.join(self.base_dir, "crm_data.db")
        self.wal_path = os.path.join(self.base_dir, "data", "state_wal.json")
        self._ensure_wal()

    def _ensure_wal(self):
        os.makedirs(os.path.dirname(self.wal_path), exist_ok=True)
        if not os.path.exists(self.wal_path):
            with open(self.wal_path, "w", encoding="utf-8") as f:
                json.dump({"entries": [], "sequence": 0}, f)

    def _get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = 1")
        return conn

    def get_unified_state(self, customer_id):
        """获取某个客户的统一状态视图

        返回:
            dict: 合并 CRM DB / lead_state / quotes / messages 的统一状态
        """
        conn = self._get_db()
        try:
            customer = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (customer_id,)
            ).fetchone()

            if not customer:
                return {
                    "customer_id": customer_id,
                    "exists": False,
                    "lead_state": "UNKNOWN",
                    "sync_state": "UNKNOWN",
                    "divergences": [],
                }

            customer = dict(customer)
            messages = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM messages WHERE customer_id = ? ORDER BY created_at DESC LIMIT 10",
                    (customer_id,),
                ).fetchall()
            ]

            quotes = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM quotes WHERE customer_id = ? ORDER BY created_at DESC",
                    (customer_id,),
                ).fetchall()
            ]

            orders = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
                    (customer_id,),
                ).fetchall()
            ]

            lead_state = customer.get("lead_state", "NEW") or "NEW"
            sync_state = LEAD_TO_SYNC_MAP.get(lead_state, "NEW")

            # 分歧检测
            divergences = self._detect_divergences(
                customer, messages, quotes, lead_state
            )

            # 最近报价
            latest_quote = quotes[0] if quotes else None

            return {
                "customer_id": customer_id,
                "exists": True,
                "customer_data": customer,
                "lead_state": lead_state,
                "sync_state": sync_state,
                "sales_stage": sync_state,
                "recent_messages": messages[:5],
                "pricing_history": [
                    {
                        "quote_id": q["id"],
                        "amount": q.get("total_amount"),
                        "currency": q.get("currency", "USD"),
                        "status": q.get("status"),
                        "timestamp": q.get("created_at"),
                    }
                    for q in quotes
                ],
                "latest_quote": latest_quote,
                "has_orders": len(orders) > 0,
                "active_orders": [o for o in orders if o.get("status") in (
                    "pending_approval", "confirmed", "in_production"
                )],
                "divergences": divergences,
                "last_contact": self._derive_last_contact(customer, messages),
            }
        finally:
            conn.close()

    def _derive_last_contact(self, customer, messages):
        """推断最后联系时间"""
        if messages:
            return messages[0].get("created_at")
        return customer.get("last_contacted_at") or customer.get("created_at")

    def _detect_divergences(self, customer, messages, quotes, lead_state):
        """检测状态系统之间的分歧

        检查项:
          1. lead_state 与实际行为不匹配
          2. 状态与时间不匹配（超时未推进）
          3. 报价记录与状态不匹配
        """
        divergences = []

        # Check 1: QUOTED but no quotes
        if lead_state == "QUOTED" and not quotes:
            divergences.append({
                "type": "state_quote_mismatch",
                "detail": "状态为 QUOTED 但无报价记录",
                "severity": "warning",
                "source_a": "lead_state",
                "source_b": "quotes_table",
            })

        # Check 2: REQUESTED_PRICE but never discussed price
        if lead_state == "REQUESTED_PRICE":
            has_price_mention = any(
                "price" in (m.get("content_en", "") or "").lower() or
                "价" in (m.get("content_cn", "") or "")
                for m in messages
            )
            if not has_price_mention and messages:
                divergences.append({
                    "type": "state_intent_mismatch",
                    "detail": "状态为 REQUESTED_PRICE 但消息未提及价格",
                    "severity": "info",
                    "source_a": "lead_state",
                    "source_b": "messages",
                })

        # Check 3: HOT but last contact > 7 days (should be COLD)
        if lead_state == "HOT" and messages:
            try:
                last_msg_time = messages[0].get("created_at", "")
                if last_msg_time:
                    last_dt = datetime.strptime(last_msg_time[:19], "%Y-%m-%dT%H:%M:%S")
                    if (datetime.now() - last_dt) > timedelta(days=7):
                        divergences.append({
                            "type": "state_timeout",
                            "detail": f"HOT 但最后联系超过7天，应为 COLD",
                            "severity": "warning",
                            "source_a": "lead_state",
                            "source_b": "time_inference",
                        })
            except (ValueError, TypeError):
                pass

        # Check 4: NEGOTIATING but no quote history
        if lead_state == "NEGOTIATING" and not quotes:
            divergences.append({
                "type": "state_negotiation_no_quote",
                "detail": "NEGOTIATING 但无报价记录",
                "severity": "warning",
                "source_a": "lead_state",
                "source_b": "quotes_table",
            })

        return divergences

    def get_price_history(self, customer_id):
        """获取客户历史报价（价格一致性检查用）"""
        conn = self._get_db()
        try:
            quotes = conn.execute(
                "SELECT * FROM quotes WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
            return [
                {
                    "quote_id": q["id"],
                    "amount": q["total_amount"],
                    "currency": q.get("currency", "USD"),
                    "status": q["status"],
                    "timestamp": q["created_at"],
                }
                for q in quotes
            ]
        finally:
            conn.close()

    def check_action_state_compatibility(self, action_type, sync_state):
        """检查动作与当前状态是否兼容

        参数:
            action_type: send_intro|send_followup|send_quote|send_negotiation|...
            sync_state: StateSyncEngine 状态

        返回:
            dict: {compatible, matrix_result, reason}
        """
        matrix = ACTION_STATE_MATRIX.get(action_type, {})
        result = matrix.get(sync_state, "BLOCK")
        if result == "ALLOW":
            return {"compatible": True, "matrix_result": "ALLOW", "reason": None}
        elif result == "MODIFY":
            return {
                "compatible": True,
                "matrix_result": "MODIFY",
                "reason": f"{action_type} 在 {sync_state} 状态下受限",
            }
        else:
            return {
                "compatible": False,
                "matrix_result": "BLOCK",
                "reason": f"{action_type} 不允许在 {sync_state} 状态下执行",
            }

    def assess_risk(self, intent):
        """评估动作风险等级"""
        action_type = INTENT_TO_ACTION.get(intent, "send_followup")
        return ACTION_RISK.get(action_type, "low")

    def register_action(self, customer_id, action_type, payload):
        """记录动作到 WAL（write-ahead log），重启后恢复

        参数:
            customer_id: 客户ID
            action_type: 动作类型
            payload: 动作内容 dict

        返回:
            dict: {sequence, timestamp, wal_id}
        """
        with _WAL_LOCK:
            try:
                with open(self.wal_path, "r", encoding="utf-8") as f:
                    wal = json.load(f)
            except (json.JSONDecodeError, OSError):
                wal = {"entries": [], "sequence": 0}

            seq = wal["sequence"] + 1
            entry = {
                "seq": seq,
                "ts": datetime.now().isoformat(),
                "customer_id": customer_id,
                "action_type": action_type,
                "payload": payload,
            }
            wal["entries"].append(entry)
            wal["sequence"] = seq

            # 最多保留 10000 条
            if len(wal["entries"]) > 10000:
                wal["entries"] = wal["entries"][-5000:]

            with open(self.wal_path, "w", encoding="utf-8") as f:
                json.dump(wal, f, ensure_ascii=False, indent=2)

        return {"sequence": seq, "timestamp": entry["ts"], "wal_id": f"WAL-{seq}"}

    def register_agent_action(self, customer_id, agent_id, action_type, payload=None):
        """增强版 register_action，增加 agent_id 身份追踪"""
        payload = dict(payload or {})
        payload["source_agent"] = agent_id
        return self.register_action(customer_id, action_type, payload)

    def record_price_snapshot(self, customer_id, snapshot):
        """记录价格快照到 WAL"""
        return self.register_action(customer_id, "price_snapshot", {
            "snapshot_preview": {k: str(v)[:80] for k, v in (snapshot or {}).items()},
            "snapshot_keys": list((snapshot or {}).keys()),
        })

    def get_agent_session_summary(self):
        """从 WAL 统计各 Agent 活跃度"""
        try:
            with open(self.wal_path, "r", encoding="utf-8") as f:
                wal = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        entries = wal.get("entries", [])
        agent_counts = {}
        for entry in entries[-500:]:
            payload = entry.get("payload", {})
            agent = payload.get("source_agent") or payload.get("agent")
            if agent:
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
        return agent_counts

    def get_wal_history(self, customer_id=None, limit=100):
        """获取 WAL 历史"""
        try:
            with open(self.wal_path, "r", encoding="utf-8") as f:
                wal = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        entries = wal.get("entries", [])
        if customer_id:
            entries = [e for e in entries if e.get("customer_id") == customer_id]
        return entries[-limit:]
