"""Follow-up Engine 2.0 — 转化驱动跟进系统

不是「提醒」，是把沉默客户拉回成交路径。

按状态+时间决定跟进策略:
  PRICING     +24h → 温和提醒
  NEGOTIATING +12h → 紧迫感推进
  HOT         +6h  → PI推进
  COLD        +7d  → 再激活
"""
import os
import sys
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ai_overlay.crm_bridge import get_customer, get_customer_messages

logger = logging.getLogger("followup_v2")

# ── 按状态的跟进策略 ─────────────────────────────────────

STATE_FOLLOWUP_STRATEGY = {
    "PRICING": {
        "delay_hours": 24,
        "max_followups": 3,
        "interval_hours": 48,
        "tone_escalation": True,  # 语气逐步加强
        "label": "报价跟进",
    },
    "NEGOTIATING": {
        "delay_hours": 12,
        "max_followups": 3,
        "interval_hours": 24,
        "tone_escalation": True,
        "label": "谈判跟进",
    },
    "CLOSING": {
        "delay_hours": 6,
        "max_followups": 4,
        "interval_hours": 12,
        "tone_escalation": True,
        "label": "成交跟进",
    },
    "FOLLOWUP": {
        "delay_hours": 48,
        "max_followups": 2,
        "interval_hours": 72,
        "tone_escalation": False,
        "label": "常规跟进",
    },
    "COLD": {
        "delay_hours": 168,  # 7天
        "max_followups": 1,
        "interval_hours": 0,
        "tone_escalation": False,
        "label": "再激活",
    },
    "HOT": {
        "delay_hours": 6,
        "max_followups": 5,
        "interval_hours": 12,
        "tone_escalation": True,
        "label": "高意向紧追",
    },
}

# ── 跟进话术（按状态+语气分级） ─────────────────────────

FOLLOWUP_SCRIPTS = {
    "PRICING": {
        1: "Hi {name}, just checking if you had time to review the quote. Happy to adjust anything!",
        2: "Hi {name}, any questions on the quotation? I can also prepare alternative options.",
        3: "{name}, the price is valid until this week. Let me know if you'd like to proceed.",
    },
    "NEGOTIATING": {
        1: "Hi {name}, I understand you're comparing options. Can I help clarify any details?",
        2: "{name}, we can still lock today's price — but I'd need to confirm by end of day.",
        3: "Production slot is filling up this week, {name}. Want me to reserve it for you?",
    },
    "CLOSING": {
        1: "Hi {name}, ready to proceed? I can send the PI right away.",
        2: "{name}, we can start production this week if you confirm today.",
        3: "Should I prepare the invoice for you, {name}?",
        4: "{name}, the deposit is only 30% to secure your production slot.",
    },
    "HOT": {
        1: "Hi {name}, I've prepared your PI. Shall I send it over?",
        2: "{name}, your production slot is available — just need your confirmation.",
        3: "Let me lock the price for you, {name}. OK to proceed?",
    },
    "FOLLOWUP": {
        1: "Hi {name}, just checking in. Any updates on your end?",
        2: "{name}, we have some new options that might interest you.",
    },
    "COLD": {
        1: "Hi {name}, it's been a while! We have new arrivals that might catch your eye.",
    },
}


# ── 跟进生成器 ──────────────────────────────────────────

class FollowupV2:
    """跟进 V2 — 按状态+次数生成跟进消息"""

    @staticmethod
    def get_strategy(state):
        """获取状态的跟进配置"""
        return STATE_FOLLOWUP_STRATEGY.get(state)

    @staticmethod
    def generate(customer_id, state, followup_count=1):
        """生成跟进消息

        参数:
            customer_id: CRM 客户 ID
            state: 当前销售状态
            followup_count: 第几次跟进（从1开始）

        返回:
            dict: {message, strategy, tone_level, max_followups}
        """
        customer = get_customer(customer_id)
        name = customer["name"] if customer else "Customer"

        scripts = FOLLOWUP_SCRIPTS.get(state, FOLLOWUP_SCRIPTS["FOLLOWUP"])
        # 找到不超过当前次数的最高级别话术
        tone_level = min(followup_count, max(scripts.keys()))
        message = scripts.get(tone_level, scripts.get(1, "Hi {name}, just following up."))
        message = message.replace("{name}", name)

        strategy = STATE_FOLLOWUP_STRATEGY.get(state, STATE_FOLLOWUP_STRATEGY["FOLLOWUP"])

        return {
            "message": message,
            "strategy": strategy["label"],
            "tone_level": tone_level,
            "max_followups": strategy["max_followups"],
            "is_last": followup_count >= strategy["max_followups"],
        }

    @staticmethod
    def should_followup(state, hours_since_last_message, followup_count=1):
        """判断当前是否应该跟进

        返回:
            dict: {should, reason, delay_hours_left}
        """
        strategy = STATE_FOLLOWUP_STRATEGY.get(state)
        if not strategy:
            return {"should": False, "reason": f"状态 {state} 无跟进策略"}

        if followup_count >= strategy["max_followups"]:
            return {"should": False, "reason": f"已达最大跟进次数 ({strategy['max_followups']})"}

        needed = strategy["delay_hours"]
        if hours_since_last_message >= needed:
            return {"should": True, "reason": f"已过 {hours_since_last_message}h >= 策略 {needed}h"}

        return {
            "should": False,
            "reason": f"未到跟进时机 ({hours_since_last_message}h < {needed}h)",
            "delay_hours_left": needed - hours_since_last_message,
        }
