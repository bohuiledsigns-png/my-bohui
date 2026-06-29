"""Followup Engine — 自动跟进收入引擎

负责客户跟进节奏:
  24h 无回复 → 轻量提醒
  3天 无成交 → 二次激活
  7天 沉默   → 再营销话术

这是一个主动销售节奏系统，不是被动通知。
"""
import os
import sys
import json
import time
import sqlite3
import logging
import threading
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

logger = logging.getLogger("followup")

# ── 引入稳定层 ──────────────────────────────────────────

from ai_overlay.stabilization import FollowUpGuard, ConversationLock

# ── 跟进规则配置 ─────────────────────────────────────────

FOLLOWUP_RULES = [
    {
        "name": "24h_checkin",
        "label": "24小时跟进",
        "delay_hours": 24,
        "state_filter": ("QUALIFYING", "PRICING", "NEGOTIATING"),
        "max_times": 2,
        "interval_hours": 48,
    },
    {
        "name": "3day_reactivate",
        "label": "3天二次激活",
        "delay_hours": 72,
        "state_filter": ("PRICING", "NEGOTIATING"),
        "max_times": 3,
        "interval_hours": 72,
    },
    {
        "name": "7day_remarketing",
        "label": "7天再营销",
        "delay_hours": 168,  # 7天
        "state_filter": ("COLD", "FOLLOWUP"),
        "max_times": 1,
        "interval_hours": 0,
    },
    {
        "name": "1h_urgent_followup",
        "label": "1小时紧急跟进",
        "delay_hours": 1,
        "state_filter": ("CLOSING",),
        "max_times": 3,
        "interval_hours": 2,
    },
]

# ── 跟进话术模板（降级用，优先用 AI 生成） ──────────────

_FOLLOWUP_TEMPLATES = {
    "24h_checkin": [
        "Hi {name}, just checking if you saw my previous message. Happy to help if you have any questions!",
        "Hey {name}, any thoughts on the product info I shared? Let me know if you need more details.",
    ],
    "3day_reactivate": [
        "Hi {name}, still thinking about the sign project? I can prepare a tailored quote if you share your size.",
        "Hey {name}, we're running a special on LED signs this month. Want me to send you the updated pricing?",
        "{name}, quick follow-up — do you have a preferred budget range? I can recommend the best option.",
    ],
    "7day_remarketing": [
        "Hi {name}, I hope everything is going well! Just a friendly reminder that we're here whenever you need signage solutions. New designs available!",
    ],
    "1h_urgent_followup": [
        "Hi {name}, ready to proceed? I can send the invoice right away so we can start production.",
        "{name}, the production slot is available this week. Shall I reserve it for you?",
    ],
}

# ── 跟进计划存储 ─────────────────────────────────────────

_FOLLOWUP_DB = os.path.join(os.path.dirname(__file__), "followup_schedule.db")


def _ensure_db():
    conn = sqlite3.connect(_FOLLOWUP_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS followup_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            rule_name TEXT NOT NULL,
            due_at TIMESTAMP NOT NULL,
            sent_count INTEGER DEFAULT 0,
            last_sent_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, rule_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS followup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            rule_name TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'sent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# ── 调度引擎 ────────────────────────────────────────────

class FollowupScheduler:
    """跟进调度器 — 决定谁在什么时候被跟进"""

    def __init__(self):
        _ensure_db()
        self._running = False
        self._thread = None

    def schedule(self, customer_id, state):
        """根据客户状态创建跟进计划"""
        now = datetime.now()
        conn = sqlite3.connect(_FOLLOWUP_DB)
        for rule in FOLLOWUP_RULES:
            if state in rule["state_filter"]:
                due = now + timedelta(hours=rule["delay_hours"])
                conn.execute("""
                    INSERT OR IGNORE INTO followup_schedule
                    (customer_id, rule_name, due_at, status)
                    VALUES (?, ?, ?, 'pending')
                """, (customer_id, rule["name"], due.isoformat()))
        conn.commit()
        conn.close()

    def get_due(self):
        """获取所有到期的跟进任务"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(_FOLLOWUP_DB)
        rows = conn.execute("""
            SELECT * FROM followup_schedule
            WHERE status = 'pending' AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT 50
        """, (now,)).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            # 补充客户信息（从 CRM 数据库）
            try:
                crm = sqlite3.connect(DB_PATH)
                crm.row_factory = sqlite3.Row
                c = crm.execute(
                    "SELECT name, country, lead_state FROM customers WHERE id=?",
                    (d["customer_id"],)
                ).fetchone()
                crm.close()
                if c:
                    d["customer_name"] = c["name"]
                    d["country"] = c["country"]
                    d["lead_state"] = c["lead_state"]
            except Exception:
                d["customer_name"] = f"Customer#{d['customer_id']}"
            results.append(d)
        return results

    def mark_sent(self, followup_id, customer_id, rule_name):
        """标记跟进已发送"""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(_FOLLOWUP_DB)
        # 更新计数
        conn.execute("""
            UPDATE followup_schedule
            SET sent_count = sent_count + 1,
                last_sent_at = ?,
                status = 'sent'
            WHERE id = ?
        """, (now, followup_id))
        # 检查是否需要重新调度
        for rule in FOLLOWUP_RULES:
            if rule["name"] == rule_name:
                row = conn.execute(
                    "SELECT sent_count FROM followup_schedule WHERE id=?",
                    (followup_id,)
                ).fetchone()
                if row and row[0] < rule["max_times"] and rule["interval_hours"] > 0:
                    next_due = datetime.now() + timedelta(hours=rule["interval_hours"])
                    conn.execute("""
                        INSERT OR REPLACE INTO followup_schedule
                        (customer_id, rule_name, due_at, sent_count, last_sent_at, status)
                        VALUES (?, ?, ?, ?, ?, 'pending')
                    """, (customer_id, rule_name, next_due.isoformat(), row[0], now))
        conn.commit()
        conn.close()

    def clear(self, customer_id):
        """清除客户所有跟进计划（客户回复时调用）"""
        conn = sqlite3.connect(_FOLLOWUP_DB)
        conn.execute(
            "DELETE FROM followup_schedule WHERE customer_id=?",
            (customer_id,)
        )
        conn.commit()
        conn.close()
        logger.info(f"[Followup] 已清除客户#{customer_id}的跟进计划")


# ── 跟进消息生成 ────────────────────────────────────────

def _generate_followup_message(customer_name, rule_name, customer_id=None):
    """生成跟进消息

    优先用 AI 生成个性化内容，降级用模板。
    """
    # 尝试用 AI 引擎生成
    if customer_id:
        try:
            from ai_engine import get_ai_followup_message
            result = get_ai_followup_message(customer_id)
            if result and not result.get("error"):
                return result.get("message", "")
        except Exception:
            pass

    # 降级用模板
    templates = _FOLLOWUP_TEMPLATES.get(rule_name, [])
    if templates:
        import random
        idx = hash(str(customer_id) + rule_name + datetime.now().strftime("%Y%m%d")) % len(templates)
        msg = templates[idx].format(name=customer_name)
        return msg
    return f"Hi {customer_name}, just following up. Let me know if you need any help!"


# ── 调度器主循环 ────────────────────────────────────────

class FollowupEngine:
    """跟进引擎 — 独立线程运行，定期检查并发送跟进"""

    def __init__(self, check_interval=300):  # 默认每5分钟检查
        self.scheduler = FollowupScheduler()
        self.check_interval = check_interval
        self._running = False
        self._thread = None

    def start(self):
        """后台启动跟进引擎"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"[Followup] 跟进引擎已启动 (检查间隔={self.check_interval}s)")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[Followup] tick error: {e}")
            time.sleep(self.check_interval)

    def _tick(self):
        """一次检查周期"""
        due_items = self.scheduler.get_due()
        if not due_items:
            return

        logger.info(f"[Followup] 本轮有 {len(due_items)} 个跟进任务到期")

        for item in due_items:
            try:
                customer_name = item.get("customer_name", "Customer")
                rule_name = item.get("rule_name", "24h_checkin")
                customer_id = item["customer_id"]
                followup_id = item["id"]
                lead_state = item.get("lead_state", "FOLLOWUP")

                # ── FollowUpGuard: 检查是否允许跟进 ──
                guard = FollowUpGuard.can_trigger(customer_id, lead_state)
                if not guard["allowed"]:
                    logger.info(f"[Followup] ⏭️ {customer_name} ({rule_name}): {guard['reason']}")
                    # 暂时跳过，保留在队列中下次再检查
                    continue

                # 生成跟进消息
                msg = _generate_followup_message(customer_name, rule_name, customer_id)

                # 通过 CRM 的 WhatsApp 发送
                try:
                    from ai_overlay.crm_bridge import send_whatsapp
                    send_result = send_whatsapp(msg, customer_name)
                    if send_result.get("ok", True):
                        status = "sent"
                    else:
                        status = "failed"
                except Exception:
                    status = "failed"

                # 记录
                conn = sqlite3.connect(_FOLLOWUP_DB)
                conn.execute(
                    "INSERT INTO followup_log (customer_id, rule_name, message, status) VALUES (?,?,?,?)",
                    (customer_id, rule_name, msg[:200], status)
                )
                conn.commit()
                conn.close()

                if status == "sent":
                    # 通知 ConversationLock 已发送跟进
                    ConversationLock.record_message(customer_id, direction="followup")
                    self.scheduler.mark_sent(followup_id, customer_id, rule_name)
                    logger.info(f"[Followup] ✅ {customer_name} ({rule_name})")

            except Exception as e:
                logger.error(f"[Followup] ❌ item error: {e}")


# ── 单例 ────────────────────────────────────────────────

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = FollowupEngine()
    return _engine


def start_followup_engine(check_interval=300):
    """快捷启动"""
    eng = get_engine()
    eng.check_interval = check_interval
    eng.start()
    return eng


# ── 快捷: 客户回复时重置跟进 ────────────────────────────

def on_customer_reply(customer_id, new_state=None):
    """客户回复时调用，重置跟进节奏"""
    eng = get_engine()
    eng.scheduler.clear(customer_id)
    if new_state:
        eng.scheduler.schedule(customer_id, new_state)
