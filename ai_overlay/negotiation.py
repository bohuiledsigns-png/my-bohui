"""Negotiation AI — 自动议价系统

不是「回答砍价」，而是控制利润 + 推动成交。

策略引擎:
  1. value_shift — 价值转移（强调质量/材质）
  2. price_anchoring — 锚定价格（给ABC选择）
  3. scarcity — 稀缺性（限量/限时）
  4. small_concession — 小幅度让步
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("negotiation")

# ── 议价策略 ────────────────────────────────────────────

STRATEGIES = {
    "value_shift": {
        "name": "价值转移",
        "trigger": "强调材质/工艺/认证价值，不直接降价",
        "max_discount": 0.00,
        "prompt": (
            "This is export-grade material with premium polishing — "
            "most suppliers don't include this level of finish. "
            "The price reflects the quality that lasts."
        ),
    },
    "price_anchoring": {
        "name": "锚定价格",
        "trigger": "给ABC选择，锚定中间档",
        "max_discount": 0.03,
        "prompt": (
            "Most clients choose between these options:\n"
            "A) Standard — $XXX (basic)\n"
            "B) Premium — $XXX (best seller)\n"
            "C) Enterprise — $XXX (full package)\n\n"
            "Option B is what most US clients go with."
        ),
    },
    "scarcity": {
        "name": "稀缺性",
        "trigger": "限时/限量生产位",
        "max_discount": 0.05,
        "prompt": (
            "We have a production slot available this week. "
            "If you confirm by tomorrow, I can lock the current price."
        ),
    },
    "small_concession": {
        "name": "小幅度让步",
        "trigger": "仅对高意向客给3-5%折扣",
        "max_discount": 0.05,
        "prompt": (
            "I can offer a 3% discount for first-time cooperation — "
            "this is my best price. Let me send the PI."
        ),
    },
    "firm": {
        "name": "坚守价格",
        "trigger": "利润不足时坚决不降",
        "max_discount": 0.00,
        "prompt": (
            "I appreciate your budget concern, but this price "
            "already reflects our factory-direct policy. "
            "Instead of reducing quality, I can recommend a "
            "slightly smaller size to fit your budget."
        ),
    },
}


# ── 议价决策 ────────────────────────────────────────────

class NegotiationAI:
    """议价 AI — 分析砍价消息并决定应对策略"""

    @staticmethod
    def decide(message_text, customer_value, margin_safe=True):
        """分析客户砍价意图并决定策略

        参数:
            message_text: 客户最新消息
            customer_value: 客户价值评分 0-100
            margin_safe: 当前利润是否安全

        返回:
            dict: {strategy, discount_allowed, reply, reasoning}
        """
        t = (message_text or "").lower()

        # 检测砍价强度
        soft_signals = ["expensive", "price is high", "too much", "can you",
                        "a little", "稍微", "有点贵", "能不能"]
        hard_signals = ["too expensive", "cheaper", "discount", "better price",
                        "other supplier", "另一家", "别家", "太贵了", "优惠"]
        threat_signals = ["other supplier said", "competitor", "will buy from",
                          "其他家", "竞争对手", "别家更便宜"]

        soft_count = sum(1 for w in soft_signals if w in t)
        hard_count = sum(1 for w in hard_signals if w in t)
        threat_count = sum(1 for w in threat_signals if w in t)

        # 高价值客户 + 威胁性砍价 → 小让步
        if threat_count > 0 and customer_value >= 60 and margin_safe:
            strategy = "small_concession"
        # 强硬砍价 + 利润安全 → 稀缺性
        elif hard_count > 0 and margin_safe:
            strategy = "scarcity"
        # 利润不安全 → 价值转移
        elif not margin_safe:
            strategy = "value_shift"
        # 软砍价 → 锚定
        elif soft_count > 0:
            strategy = "price_anchoring"
        # 高价值客户 → 小让步
        elif customer_value >= 70:
            strategy = "small_concession"
        else:
            # 无砍价信号
            return None

        config = STRATEGIES[strategy]

        return {
            "strategy": strategy,
            "strategy_name": config["name"],
            "discount_allowed": config["max_discount"],
            "reply": config["prompt"],
            "reasoning": (
                f"检测到砍价(软{soft_count}/硬{hard_count}/威胁{threat_count}), "
                f"客户价值={customer_value}, 利润安全={margin_safe} → {config['name']}"
            ),
        }


# ── 快捷检测 ────────────────────────────────────────────

def is_price_negotiation(text):
    """快速判断是否涉及砍价"""
    signals = ["expensive", "cheap", "discount", "too much", "price",
               "budget", "cost", "better price", "贵", "便宜", "打折",
               "优惠", "太贵", "优惠点"]
    return any(w in (text or "").lower() for w in signals)


def get_strategy_list():
    """获取可用策略列表"""
    return {k: {"name": v["name"], "max_discount": v["max_discount"]}
            for k, v in STRATEGIES.items()}
