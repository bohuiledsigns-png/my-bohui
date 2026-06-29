"""Closer Agent — 成交型销售

特点：紧迫感、逼单、限时优惠
适用场景：A类客户、FINAL状态、高意向但犹豫的客户
策略：限时优惠，制造FOMO
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class CloserAgent:
    """Closer Agent — 成交型销售代表"""

    AGENT_ID = "closer_agent"
    NAME = "Closer (Diana)"
    STRATEGY = "urgency_driven"
    PRICING_MODE = "limited_time_offer"

    @staticmethod
    def persona_prompt() -> str:
        return (
            "You are Diana, a Closer sales representative. Your style is high-urgency and decisive.\n"
            "You specialize in getting customers to make a decision NOW.\n"
            "Rules:\n"
            "- Create genuine urgency: limited production capacity this month\n"
            "- Use A/B/C option framing: present options with clear recommendation\n"
            "- Time-bound offers: 'This pricing is valid until Friday'\n"
            "- Use social proof: 'Several hotels in your area have already ordered'\n"
            "- Direct ask: 'Shall I prepare the invoice for you?'\n"
            "- Overcome last objections with guarantees, not discounts\n"
            "- Offer a small closing incentive if needed (up to 10%)\n"
            "- Never let the conversation end without a clear next step toward close"
        )

    @staticmethod
    def pricing_strategy(base_price: float, region_multiplier: float = 1.0) -> dict:
        """Closer定价策略：限时优惠"""
        standard = base_price * region_multiplier
        closing_discount = round(standard * 0.08, 2)
        final = round(standard - closing_discount, 2)
        return {
            "agent": "closer",
            "anchor_price": round(standard, 2),
            "discount": closing_discount,
            "final_price": final,
            "discount_note": (
                f"Today's closing price: ${final:.0f} (save ${closing_discount:.0f}). "
                f"Regular price: ${standard:.0f}. Offer expires in 48 hours."
            ),
            "urgency": "critical",
        }

    @staticmethod
    def generate_reply(customer_msg: str, context: dict = None) -> str:
        """生成Closer风格的回复（指令注入）"""
        persona = CloserAgent.persona_prompt()
        pricing = CloserAgent.pricing_strategy(
            base_price=context.get("base_price", 100) if context else 100,
            region_multiplier=context.get("region_multiplier", 1.0) if context else 1.0,
        )
        return (
            f"[AGENT: {CloserAgent.NAME} | STRATEGY: {CloserAgent.STRATEGY}]\n"
            f"{persona}\n\n"
            f"Pricing Strategy (Limited Time):\n{pricing['discount_note']}\n"
            f"Urgency: {pricing['urgency']}\n"
            f"Closing price: ${pricing['final_price']} (was ${pricing['anchor_price']})\n"
            "=== GENERATE YOUR REPLY BASED ON THE ABOVE ==="
        )
