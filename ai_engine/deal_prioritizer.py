"""V4 Deal Prioritizer — 客户优先级排序引擎

将客户按成交概率分为 A/B/C 三类，驱动自动销售决策。

评分维度:
  - sales_state 权重 (NEW=10, NEEDS_ANALYSIS=35, BUDGET=60, OBJECTION=45, FINAL=85)
  - v3 成交转化分 (conversion_score * 0.3)
  - 消息数量 (min(count*5, 15))
  - 回复速度 (fast=+15, medium=+10, slow=+5)
  - 客户国家 (HIGH=+10, MID=+5, LOW=0)
  - 报价查看次数 (+10 if > 0)
"""

import sys
import os
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db


# ==================== 评分权重配置 ====================

_STATE_WEIGHTS = {
    "NEW": 10,
    "NEEDS_ANALYSIS": 35,
    "BUDGET": 60,
    "OBJECTION": 45,
    "FINAL": 85,
}

_COUNTRY_TIERS = {
    "HIGH": {"bonus": 10, "countries": ["US", "USA", "UK", "GBR", "Germany", "DEU", "Australia", "AUS",
                                         "Canada", "CAN", "France", "FRA", "Singapore", "SGP", "Japan", "JPN"]},
    "MID": {"bonus": 5, "countries": ["UAE", "ARE", "Saudi Arabia", "SAU", "Spain", "ESP", "Italy", "ITA",
                                       "South Korea", "KOR", "New Zealand", "NZL", "Switzerland", "CHE"]},
    "LOW": {"bonus": 0, "countries": ["India", "IND", "Pakistan", "PAK", "Bangladesh", "BGD",
                                       "Nigeria", "NGA", "Kenya", "KEN", "Vietnam", "VNM"]},
}

_COUNTRY_BONUS_MAP = {}
for tier, cfg in _COUNTRY_TIERS.items():
    for c in cfg["countries"]:
        _COUNTRY_BONUS_MAP[c.upper()] = cfg["bonus"]


class DealPrioritizer:
    """客户优先级排序引擎"""

    def compute_priority(self, customer_id):
        """计算单个客户优先级分数

        Args:
            customer_id: 客户 ID

        Returns:
            dict: {priority_score, priority_class, priority_action, reason}
        """
        conn = get_db()

        # 1. 获取客户基本信息
        cust = conn.execute(
            "SELECT id, country, status FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()
        if not cust:
            conn.close()
            return {"error": "customer not found"}

        country = (cust["country"] or "").upper()

        # 2. 获取 v3 最新成交记录
        conv = conn.execute(
            """SELECT final_state, conversion_score, quote_amount, quote_sent
               FROM v3_conversions
               WHERE customer_id=? AND final_result != 'open'
               ORDER BY id DESC LIMIT 1""",
            (customer_id,)
        ).fetchone()

        # 3. 获取消息统计
        msg_row = conn.execute(
            """SELECT COUNT(*) as msg_count,
                      AVG(CASE WHEN direction='sent' THEN 0 ELSE 1 END) as reply_ratio
               FROM messages WHERE customer_id=?""",
            (customer_id,)
        ).fetchone()

        # 4. 获取现有 v4 状态
        v4 = conn.execute(
            "SELECT quote_view_count, last_activity_at, push_count FROM v4_customer_state WHERE customer_id=?",
            (customer_id,)
        ).fetchone()

        conn.close()

        # ====== 评分计算 ======
        reasons = []
        score = 0

        # --- state weight ---
        state = conv["final_state"] if conv else "NEW"
        state_w = _STATE_WEIGHTS.get(state, 10)
        score += state_w
        reasons.append(f"state:{state}(+{state_w})")

        # --- conversion_score ---
        if conv and conv["conversion_score"]:
            cs_bonus = int(conv["conversion_score"] * 0.3)
            score += cs_bonus
            reasons.append(f"conv_score(+{cs_bonus})")

        # --- message count ---
        msg_count = msg_row["msg_count"] if msg_row else 0
        msg_bonus = min(msg_count * 5, 15)
        score += msg_bonus
        reasons.append(f"msgs:{msg_count}(+{msg_bonus})")

        # --- reply speed ---
        reply_ratio = msg_row["reply_ratio"] if msg_row and msg_row["reply_ratio"] else 0
        if reply_ratio > 0.5:
            speed_bonus = 15
            reasons.append("reply:fast(+15)")
        elif reply_ratio > 0.2:
            speed_bonus = 10
            reasons.append("reply:medium(+10)")
        else:
            speed_bonus = 5
            reasons.append("reply:slow(+5)")
        score += speed_bonus

        # --- country bonus ---
        country_bonus = _COUNTRY_BONUS_MAP.get(country, 3)
        score += country_bonus
        reasons.append(f"country:{country}(+{country_bonus})")

        # --- quote viewed ---
        if v4 and v4["quote_view_count"] and v4["quote_view_count"] > 0:
            score += 10
            reasons.append(f"quote_viewed(+10)")

        # 限制 0-100
        score = max(0, min(100, score))

        # ====== 分类 ======
        if score >= 70:
            cls = "A"
            action = "CLOSE_NOW"
        elif score >= 40:
            cls = "B"
            action = "PUSH"
        else:
            cls = "C"
            action = "HOLD"

        return {
            "customer_id": customer_id,
            "priority_score": score,
            "priority_class": cls,
            "priority_action": action,
            "reason": "; ".join(reasons),
        }

    def batch_reprioritize(self, limit=100):
        """批量重新计算所有活跃客户的优先级

        Args:
            limit: 最大处理客户数

        Returns:
            list: [priority_result, ...]
        """
        conn = get_db()
        active = conn.execute(
            """SELECT id FROM customers
               WHERE status NOT IN ('lost', 'deleted')
               ORDER BY updated_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()

        results = []
        now = datetime.now().isoformat()
        for row in active:
            result = self.compute_priority(row["id"])
            if "error" in result:
                continue
            results.append(result)

            # 写入 v4_customer_state
            self._save_state(result)

        return results

    def _save_state(self, result):
        """将优先级结果持久化到 v4_customer_state"""
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM v4_customer_state WHERE customer_id=?",
            (result["customer_id"],)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE v4_customer_state SET
                   priority_score=?, priority_class=?, priority_action=?,
                   priority_reason=?, priority_updated_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE customer_id=?""",
                (result["priority_score"], result["priority_class"],
                 result["priority_action"], result["reason"],
                 result["customer_id"])
            )
        else:
            conn.execute(
                """INSERT INTO v4_customer_state
                   (customer_id, priority_score, priority_class, priority_action,
                    priority_reason, priority_updated_at)
                   VALUES (?,?,?,?,?, CURRENT_TIMESTAMP)""",
                (result["customer_id"], result["priority_score"],
                 result["priority_class"], result["priority_action"],
                 result["reason"])
            )
        conn.commit()
        conn.close()

    def get_by_class(self, class_name):
        """获取指定分类的客户列表

        Args:
            class_name: 'A', 'B', or 'C'

        Returns:
            list: [dict, ...]
        """
        conn = get_db()
        rows = conn.execute(
            """SELECT cs.*, c.name, c.country, c.whatsapp
               FROM v4_customer_state cs
               JOIN customers c ON cs.customer_id = c.id
               WHERE cs.priority_class=? AND c.status NOT IN ('lost','deleted')
               ORDER BY cs.priority_score DESC""",
            (class_name,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_priority_summary(self):
        """获取 A/B/C 三类数量汇总"""
        conn = get_db()
        rows = conn.execute(
            """SELECT priority_class, COUNT(*) as cnt
               FROM v4_customer_state
               GROUP BY priority_class
               ORDER BY priority_class"""
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM customers WHERE status NOT IN ('lost','deleted')"
        ).fetchone()
        conn.close()

        summary = {"total_customers": total["cnt"] if total else 0, "classes": {}}
        for r in rows:
            summary["classes"][r["priority_class"]] = r["cnt"]
        for c in ["A", "B", "C"]:
            if c not in summary["classes"]:
                summary["classes"][c] = 0
        return summary

    def update_activity(self, customer_id, state="", conversion_score=0, intent=""):
        """由 RevenueEngine 调用，更新客户活动状态"""
        conn = get_db()
        existing = conn.execute(
            "SELECT id, total_messages FROM v4_customer_state WHERE customer_id=?",
            (customer_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE v4_customer_state SET
                   total_messages = total_messages + 1,
                   last_activity_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE customer_id=?""",
                (customer_id,)
            )
        else:
            conn.execute(
                """INSERT INTO v4_customer_state
                   (customer_id, total_messages, last_activity_at, priority_class)
                   VALUES (?, 1, CURRENT_TIMESTAMP, 'C')""",
                (customer_id,)
            )
        conn.commit()
        conn.close()
        # 快速重新评分（异步友好）
        result = self.compute_priority(customer_id)
        if "priority_score" in result:
            self._save_state(result)
        return result


# ==================== 快捷入口 ====================

prioritizer = DealPrioritizer()


def reprioritize_all(limit=100):
    return prioritizer.batch_reprioritize(limit=limit)
