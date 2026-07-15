"""Consultant Agent — 顾问型销售

特点：分析需求、给专业方案、建立信任
适用场景：B类客户、NEEDS_ANALYSIS状态、需要专业建议的客户
策略：市场标准价，以专业度取胜
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class ConsultantAgent:
    """Consultant Agent — 顾问型销售代表"""

    AGENT_ID = "consultant_agent"
    NAME = "Consultant (Sarah)"
    STRATEGY = "consultative"
    PRICING_MODE = "market_standard"

    @staticmethod
    def persona_prompt() -> str:
        return (
            "You are Sarah, a Product Consultant sales representative. Your style is professional and analytical.\n"
            "You believe in understanding customer needs before offering solutions.\n"
            "Rules:\n"
            "- Ask questions first: what's their business, what problem they're solving\n"
            "- Provide tailored recommendations based on their specific needs\n"
            "- Explain WHY a product fits, not just what it does\n"
            "- Use case studies and examples relevant to their industry\n"
            "- Quote market-standard pricing with clear value breakdown\n"
            "- Be patient — good decisions take time\n"
            "- Focus on long-term value, not quick discounts\n"
            "- Sound like a knowledgeable partner, not a pushy salesperson"
        )

    @staticmethod
    def pricing_strategy(base_price: float, region_multiplier: float = 1.0) -> dict:
        """Consultant定价策略：市场标准价"""
        standard = base_price * region_multiplier * 1.0
        return {
            "agent": "consultant",
            "anchor_price": round(standard, 2),
            "discount": 0,
            "final_price": round(standard, 2),
            "discount_note": f"Market standard price: ${standard:.0f}. Includes full warranty and support.",
            "urgency": "low",
        }

    @staticmethod
    def generate_reply(customer_msg: str, context: dict = None) -> str:
        """生成Consultant风格的回复（指令注入）"""
        persona = ConsultantAgent.persona_prompt()
        pricing = ConsultantAgent.pricing_strategy(
            base_price=context.get("base_price", 100) if context else 100,
            region_multiplier=context.get("region_multiplier", 1.0) if context else 1.0,
        )
        return (
            f"[AGENT: {ConsultantAgent.NAME} | STRATEGY: {ConsultantAgent.STRATEGY}]\n"
            f"{persona}\n\n"
            f"Pricing Strategy: {pricing['discount_note']}\n"
            f"Urgency: {pricing['urgency']}\n"
            f"Market price: ${pricing['final_price']}\n"
            "=== GENERATE YOUR REPLY BASED ON THE ABOVE ==="
        )
