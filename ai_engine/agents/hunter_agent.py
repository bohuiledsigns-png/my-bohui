"""Hunter Agent — 激进型销售

特点：直接报价、制造紧迫感、快速成交
适用场景：C类客户激活、价格敏感客户、犹豫不决型
策略：高报价+立即折扣，制造稀缺感
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class HunterAgent:
    """Hunter Agent — 激进型销售代表"""

    AGENT_ID = "hunter_agent"
    NAME = "Hunter (Alex)"
    STRATEGY = "aggressive"
    PRICING_MODE = "high_anchor_with_discount"

    @staticmethod
    def persona_prompt() -> str:
        return (
            "You are Alex, a Hunter sales representative. Your style is direct and aggressive.\n"
            "You believe in creating urgency and closing deals fast.\n"
            "Rules:\n"
            "- Always quote price early in the conversation\n"
            "- Create scarcity: 'limited production slots', 'special pricing today'\n"
            "- Use bold statements: 'This is the best investment for your business'\n"
            "- Offer immediate discount to create quick decision\n"
            "- Don't be afraid to push: 'If you decide today, I can offer 10% off'\n"
            "- Focus on ROI and quick wins for the customer\n"
            "- Use high anchor pricing then discount to create perceived value\n"
            "- Be confident and decisive — the customer wants a leader, not a salesperson"
        )

    @staticmethod
    def pricing_strategy(base_price: float, region_multiplier: float = 1.0) -> dict:
        """Hunter定价策略：高锚点+即时折扣"""
        anchor = base_price * region_multiplier * 1.25  # 高25%锚点
        discount = round(anchor * 0.12, 2)  # 给12%折扣
        final = round(anchor - discount, 2)
        return {
            "agent": "hunter",
            "anchor_price": round(anchor, 2),
            "discount": discount,
            "final_price": final,
            "discount_note": f"Special 12% off — valid today only! Was ${anchor:.0f}, now ${final:.0f}",
            "urgency": "high",
        }

    @staticmethod
    def generate_reply(customer_msg: str, context: dict = None) -> str:
        """生成Hunter风格的回复（由competition系统调用LLM，此方法返回agent的指令注入）"""
        persona = HunterAgent.persona_prompt()
        pricing = HunterAgent.pricing_strategy(
            base_price=context.get("base_price", 100) if context else 100,
            region_multiplier=context.get("region_multiplier", 1.0) if context else 1.0,
        )
        return (
            f"[AGENT: {HunterAgent.NAME} | STRATEGY: {HunterAgent.STRATEGY}]\n"
            f"{persona}\n\n"
            f"Pricing Strategy: {pricing['discount_note']}\n"
            f"Urgency: {pricing['urgency']}\n"
            f"Use this pricing anchor: ${pricing['anchor_price']} → discount → ${pricing['final_price']}\n"
            "=== GENERATE YOUR REPLY BASED ON THE ABOVE ==="
        )
