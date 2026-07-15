"""V4 Autonomous Sender — 自动 WhatsApp 发送器

系统自动发送:
  - 优先级推单 (A类 → 紧迫逼单)
  - 温和跟进 (B类 → 案例+价值重申)
  - 冷唤醒 (C类 → 培育内容)
  - 成交推单 (FINAL状态 → 最后逼单)
  - 风险话术 (OBJECTION状态 → 风险框架)

调用链路:
  AutonomousSender
    → 模板 / RevenueEngine.process()
    → whatsapp_engine.send_text()
    → 实际发送
"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db


# ==================== 跟进模板 ====================

_FOLLOWUP_TEMPLATES = {
    "followup_light": (
        "Hi {name}, just checking in — did you have a chance to review the options I sent earlier?\n"
        "Happy to answer any questions. No rush at all!"
    ),
    "wake_up": (
        "Hi {name}, hope you're doing well! Quick update — we're currently offering "
        "priority production scheduling for new orders this month.\n"
        "Let me know if you're still considering a sign for your business!"
    ),
    "case_study": (
        "Hi {name}, thought you might find this useful — we recently completed a similar project for "
        "a business like yours.\n\n"
        "If you'd like, I can prepare a quick design concept for your storefront. "
        "No pressure at all!"
    ),
    "risk_message": (
        "Hi {name}, I understand price is important. Many of our clients felt the same at first.\n"
        "The difference isn't just material — it's how long your sign stays looking great. "
        "A quality sign that lasts 6+ years costs less than a cheap one replaced every 2 years."
    ),
    "push_close": (
        "Hi {name}, just a heads up — we have a production slot opening up this week "
        "that I could reserve for you.\n"
        "Here are the options:\n"
        "A) {price_a}\n"
        "B) {price_b} (recommended)\n"
        "C) {price_c} (premium)\n\n"
        "Which one works best for you?"
    ),
    "final_close": (
        "Hi {name}, wanted to check one last time — we can start production "
        "immediately if you confirm today.\n"
        "A) {price_a}\n"
        "B) {price_b}\n"
        "C) {price_c}\n\n"
        "Which should I lock in for you?"
    ),
}


class AutonomousSender:
    """自动 WhatsApp 发送器"""

    def send_priority_push(self, customer_id, priority_class="B"):
        """根据优先级发送推单消息

        Args:
            customer_id: 客户 ID
            priority_class: A/B/C

        Returns:
            dict: {sent, message, error}
        """
        if priority_class == "A":
            return self._send_by_type(customer_id, "push_close")
        elif priority_class == "B":
            return self._send_by_type(customer_id, "followup_light")
        else:
            return self._send_by_type(customer_id, "wake_up")

    def send_quote(self, customer_id, price_tier="MID"):
        """发送报价消息（通过 RevenueEngine）"""
        return self._send_via_revenue(customer_id, f"Please send quote, tier {price_tier}")

    def send_followup(self, customer_id, followup_type="followup_light"):
        """发送跟进消息"""
        return self._send_by_type(customer_id, followup_type)

    def send_closing_push(self, customer_id):
        """发送成交推单"""
        return self._send_by_type(customer_id, "push_close")

    def send_by_decision(self, customer_id, brain_decision):
        """根据决策大脑的输出发送

        Args:
            customer_id: 客户 ID
            brain_decision: ConversionBrain.decide() 的输出 dict

        Returns:
            dict: 发送结果
        """
        content_type = brain_decision.get("content_type", "none")
        if content_type == "none":
            return {"sent": False, "reason": "brain decided not to send"}
        return self._send_by_type(customer_id, content_type)

    def _send_by_type(self, customer_id, content_type):
        """按内容类型发送消息

        Args:
            customer_id: 客户 ID
            content_type: followup_light|wake_up|push_close|risk_message|final_close

        Returns:
            dict: {sent, message, customer_id, error}
        """
        # 获取客户信息
        conn = get_db()
        cust = conn.execute(
            "SELECT id, name, country, whatsapp FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()

        # 获取价格信息（用于 push_close / final_close）
        v4 = conn.execute(
            """SELECT price_tier_override, priority_class
               FROM v4_customer_state WHERE customer_id=?""",
            (customer_id,)
        ).fetchone()
        conn.close()

        if not cust:
            return {"error": "customer not found", "sent": False}

        name = cust["name"] or "there"

        # 获取价格锚
        price_a, price_b, price_c = self._get_price_options(v4)

        # 构建模板
        template = _FOLLOWUP_TEMPLATES.get(content_type)
        if not template:
            return {"error": f"unknown content_type: {content_type}", "sent": False}

        try:
            text = template.format(
                name=name,
                price_a=price_a,
                price_b=price_b,
                price_c=price_c,
            )
        except KeyError:
            text = template.replace("{name}", name)

        # 记录发送（不实际发送 — 由调用方决定是否调用 whatsapp_engine）
        self._record_send(customer_id, content_type, text)

        return {
            "sent": True,
            "customer_id": customer_id,
            "content_type": content_type,
            "text": text,
        }

    def _send_via_revenue(self, customer_id, simulated_message):
        """通过 RevenueEngine 生成并发送消息"""
        conn = get_db()
        cust = conn.execute(
            "SELECT id, name, country FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()
        conn.close()

        if not cust:
            return {"error": "customer not found", "sent": False}

        try:
            from revenue_engine import RevenueEngine
            engine = RevenueEngine()
            result = engine.process(
                message=simulated_message,
                country=cust["country"] or "",
                customer_name=cust["name"] or "",
                customer_id=customer_id,
            )

            text = result.get("reply_text", "")
            self._record_send(customer_id, "revenue_generated", text)

            return {
                "sent": True,
                "customer_id": customer_id,
                "content_type": "revenue_generated",
                "text": text,
                "action": result.get("action"),
                "v3_conversion_id": result.get("v3_conversion_id"),
            }
        except Exception as e:
            return {"error": str(e), "sent": False}

    def _get_price_options(self, v4_state):
        """获取当前价格选项"""
        try:
            import sales_executor

            tier = "MID"
            if v4_state and v4_state["price_tier_override"]:
                tier = v4_state["price_tier_override"]
            elif v4_state and v4_state["priority_class"] == "A":
                tier = "HIGH"

            anchors = sales_executor._PRICE_ANCHORS.get(tier, sales_executor._PRICE_ANCHORS.get("MID", {}))
            abc = anchors.get("abc", [])
            if len(abc) >= 3:
                return abc[0]["price"], abc[1]["price"], abc[2]["price"]
        except Exception:
            pass
        return "$200-250", "$250-300", "$300-350"

    def _record_send(self, customer_id, content_type, text):
        """记录发送到 v4_customer_state + messages 表"""
        conn = get_db()
        # 更新推送计数
        conn.execute(
            """UPDATE v4_customer_state SET
               push_count = COALESCE(push_count, 0) + 1,
               last_push_at = CURRENT_TIMESTAMP,
               scheduler_state = 'pushed',
               updated_at = CURRENT_TIMESTAMP
               WHERE customer_id=?""",
            (customer_id,)
        )
        # 记录到 messages 表
        conn.execute(
            """INSERT INTO messages
               (customer_id, direction, content_en, created_at)
               VALUES (?, 'sent', ?, CURRENT_TIMESTAMP)""",
            (customer_id, text[:500])
        )
        conn.commit()
        conn.close()


# ==================== 快捷入口 ====================

sender = AutonomousSender()


def send_priority_push(customer_id, priority_class="B"):
    return sender.send_priority_push(customer_id, priority_class)
