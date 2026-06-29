"""Revenue Pressure Engine — 紧迫感生成引擎

核心问题: 「怎么让客户今天下单，而不是下个月？」

3级压力体系:
  Level 1 — 软性（soft）: 信息性紧迫感
    适用: 早期阶段、高价值客户
    话术: 价格有效期、材料成本提醒

  Level 2 — 中等（medium）: 选择性紧迫感
    适用: 报价后、谈判中
    话术: 生产位紧张、限时优惠

  Level 3 — 强硬（hard）: 行动性紧迫感
    适用: 谈判后期、准备成交
    话术: 定金锁定、错过等下一批

原则:
  - 不对新客户(NEW)用硬压力
  - 高价值客户用软压力
  - 低意向客户用中等压力
  - 成交前必须用硬压力
"""
import os
import sys
import logging
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("revenue_pressure")

# ── 三级压力话术 ──────────────────────────────────────────

PRESSURE_SCRIPTS = {
    "soft": [
        "By the way, this price is valid until the end of this month. After that, material costs may affect pricing.",
        "We're currently running a promotion for first-time clients — I can extend the same terms to you.",
        "Just a heads up, our factory enters peak season next month which may affect lead times.",
        "The current pricing is based on stable material costs. We expect an adjustment next quarter.",
    ],
    "medium": [
        "Our production slots are filling up quickly for this month. Early confirmation guarantees on-time delivery.",
        "I have a production slot available right now — if you confirm within the next few days, we can start immediately.",
        "The current pricing reflects lower material costs. We're expecting a price increase soon due to steel prices rising.",
        "We've been running at high capacity. This week's slot is still open if you'd like to secure it.",
    ],
    "hard": [
        "We have only 3 production slots remaining this month. A 30% deposit secures your slot and locks the price.",
        "If we proceed this week, I can guarantee delivery within 15 days. After that, the next available slot is next month.",
        "Let me send you the PI now — once confirmed, we start production immediately. This ensures delivery before your deadline.",
        "The factory is currently booking for next month's production. Confirm now and I can still fit you into this month's schedule.",
    ],
}

# 按状态推荐压力等级
STATE_PRESSURE_MAP = {
    "NEW": None,           # 新客户不用压力
    "QUALIFYING": None,    # 了解需求不用压力
    "PRICING": "soft",     # 报价后用软压力
    "NEGOTIATING": "medium",  # 谈判中用中等
    "CLOSING": "hard",     # 成交前用硬压力
    "HOT": "medium",       # 高意向用中等
    "FOLLOWUP": "soft",    # 跟进用软
    "COLD": None,          # 冷客户不用
}

# 特定场景压力索引
SCENARIO_PRESSURE = {
    "price_validity": {"tier": "soft", "index": 0},
    "promotion": {"tier": "soft", "index": 1},
    "peak_season": {"tier": "soft", "index": 2},
    "slot_available": {"tier": "medium", "index": 0},
    "immediate_start": {"tier": "medium", "index": 1},
    "price_adjustment": {"tier": "medium", "index": 2},
    "last_slots": {"tier": "hard", "index": 0},
    "15day_delivery": {"tier": "hard", "index": 1},
    "send_pi_now": {"tier": "hard", "index": 2},
}


class RevenuePressureEngine:
    """紧迫感生成引擎 — 在合适时机追加压力话术"""

    @staticmethod
    def select_tier(state, score=None, followup_count=0):
        """选择适合当前场景的压力等级

        参数:
            state: 当前销售状态
            score: LeadScorer 分数（可选，0-1）
            followup_count: 跟进次数

        返回:
            str or None: 压力等级 (soft/medium/hard) 或 None
        """
        tier = STATE_PRESSURE_MAP.get(state)

        if not tier:
            return None

        # 分数修正: 高意向客户降一档（保护客情关系）
        if score is not None and score >= 0.8:
            if tier == "hard":
                tier = "medium"
            elif tier == "medium":
                tier = "soft"
            elif tier == "soft":
                return None

        # 跟进次数修正: 多次跟进升一档
        if followup_count >= 3 and tier is not None:
            if tier == "soft":
                tier = "medium"
            elif tier is None:
                if state not in ("NEW", "COLD"):
                    tier = "soft"

        return tier

    @staticmethod
    def generate_pressure(tier, customer_name=None, scenario=None):
        """生成紧迫感消息

        参数:
            tier: 压力等级 (soft/medium/hard) 或 None
            customer_name: 客户名称（可选，用于个性化）
            scenario: 指定场景（可选，如 price_validity/slot_available）

        返回:
            str or None: 紧迫感消息
        """
        if not tier:
            return None

        scripts = PRESSURE_SCRIPTS.get(tier, [])
        if not scripts:
            return None

        if scenario and scenario in SCENARIO_PRESSURE:
            config = SCENARIO_PRESSURE[scenario]
            idx = config["index"]
            msg = scripts[idx] if idx < len(scripts) else scripts[0]
        else:
            msg = random.choice(scripts)

        return msg

    @staticmethod
    def append_to_reply(reply, tier, customer_name=None, scenario=None):
        """将紧迫感消息追加到现有回复后面

        参数:
            reply: 原始回复文本
            tier: 压力等级 (soft/medium/hard) 或 None
            customer_name: 客户名称（可选）
            scenario: 指定场景（可选）

        返回:
            str: 追加后的完整回复
        """
        if not tier:
            return reply

        pressure_msg = RevenuePressureEngine.generate_pressure(tier, customer_name, scenario)
        if not pressure_msg:
            return reply

        reply = reply.rstrip()
        return f"{reply}\n\n{pressure_msg}"

    @staticmethod
    def get_scenario_by_state(state, score=None):
        """根据状态获取推荐场景"""
        scenarios = {
            "PRICING": "price_validity",
            "NEGOTIATING": "slot_available" if (score or 0) >= 0.6 else "promotion",
            "CLOSING": "send_pi_now",
            "HOT": "immediate_start",
            "FOLLOWUP": "promotion",
        }
        return scenarios.get(state)

    @staticmethod
    def list_pressure_tiers():
        """列出所有压力等级（调试用）"""
        return {tier: len(scripts) for tier, scripts in PRESSURE_SCRIPTS.items()}
