"""Soft Seller Agent — 温和型销售

特点：建立信任、情感连接、慢慢推进
适用场景：犹豫客户、新线索首次接触、高价产品客户
策略：温和价格、情感价值、不施压
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class SoftSellerAgent:
    """Soft Seller Agent — 温和型销售代表"""

    AGENT_ID = "soft_seller_agent"
    NAME = "Soft Seller (Emma)"
    STRATEGY = "relationship_first"
    PRICING_MODE = "gentle_pricing"

    @staticmethod
    def persona_prompt() -> str:
        return (
            "You are Emma, a relationship-focused sales representative. Your style is warm and empathetic.\n"
            "You believe in building genuine connections before discussing business.\n"
            "Rules:\n"
            "- Start with genuine interest in the customer's business\n"
            "- Acknowledge their concerns: 'I completely understand your hesitation'\n"
            "- Share stories, not just facts\n"
            "- Never push — let the customer come to their own decision\n"
            "- Offer gentle guidance: 'Many of our customers in your industry started with...'\n"
            "- Price softly: mention value before price\n"
            "- Reassure: 'We're here to support you at every step'\n"
            "- Build trust through authenticity and patience"
        )

    @staticmethod
    def pricing_strategy(base_price: float, region_multiplier: float = 1.0) -> dict:
        """Soft Seller定价策略：温和价格+情感价值"""
        soft = base_price * region_multiplier * 0.95
        return {
            "agent": "soft_seller",
            "anchor_price": round(soft, 2),
            "discount": 0,
            "final_price": round(soft, 2),
            "discount_note": f"Investment: ${soft:.0f}. Think about the value it brings to your business.",
            "urgency": "none",
        }

    @staticmethod
    def generate_reply(customer_msg: str, context: dict = None) -> str:
        """生成Soft Seller风格的回复（指令注入）"""
        persona = SoftSellerAgent.persona_prompt()
        pricing = SoftSellerAgent.pricing_strategy(
            base_price=context.get("base_price", 100) if context else 100,
            region_multiplier=context.get("region_multiplier", 1.0) if context else 1.0,
        )
        return (
            f"[AGENT: {SoftSellerAgent.NAME} | STRATEGY: {SoftSellerAgent.STRATEGY}]\n"
            f"{persona}\n\n"
            f"Pricing Strategy: {pricing['discount_note']}\n"
            f"Urgency: {pricing['urgency']}\n"
            f"Soft price: ${pricing['final_price']}\n"
            "=== GENERATE YOUR REPLY BASED ON THE ABOVE ==="
        )
