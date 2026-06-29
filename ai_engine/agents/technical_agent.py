"""Technical Agent — 技术型销售

特点：讲参数、给数据、用规格说服
适用场景：技术型客户、工程类客户、需要详细规格的询盘
策略：价值定价（按参数报价），以技术优势证明价格合理性
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class TechnicalAgent:
    """Technical Agent — 技术型销售代表"""

    AGENT_ID = "technical_agent"
    NAME = "Technical (Mike)"
    STRATEGY = "data_driven"
    PRICING_MODE = "value_pricing"

    @staticmethod
    def persona_prompt() -> str:
        return (
            "You are Mike, a Technical Sales specialist. Your style is precise and data-driven.\n"
            "You believe in winning customers through technical superiority.\n"
            "Rules:\n"
            "- Lead with specifications: materials, dimensions, certifications\n"
            "- Provide detailed technical comparisons vs competitors\n"
            "- Use numbers and data to prove quality\n"
            "- Explain manufacturing process and quality control\n"
            "- Quote value-based pricing: break down cost by component\n"
            "- Address technical concerns with precise answers\n"
            "- Reference certifications: CE, RoHS, ISO, UV-resistant, etc.\n"
            "- Sound like an engineer who happens to sell, not a salesperson"
        )

    @staticmethod
    def pricing_strategy(base_price: float, region_multiplier: float = 1.0) -> dict:
        """Technical定价策略：价值定价（按参数报价）"""
        # 按参数分解价格
        material_cost = base_price * 0.4
        led_cost = base_price * 0.25
        labor_cost = base_price * 0.15
        markup = base_price * 0.2
        total = (material_cost + led_cost + labor_cost + markup) * region_multiplier
        return {
            "agent": "technical",
            "anchor_price": round(total, 2),
            "discount": 0,
            "final_price": round(total, 2),
            "discount_note": (
                f"Value breakdown: Materials ${material_cost:.0f} | "
                f"LED modules ${led_cost:.0f} | "
                f"Labor ${labor_cost:.0f} | "
                f"Quality margin ${markup:.0f} | "
                f"Total: ${total:.0f}"
            ),
            "urgency": "low",
            "breakdown": {
                "materials": round(material_cost, 2),
                "led_modules": round(led_cost, 2),
                "labor": round(labor_cost, 2),
                "quality_margin": round(markup, 2),
                "total": round(total, 2),
            },
        }

    @staticmethod
    def generate_reply(customer_msg: str, context: dict = None) -> str:
        """生成Technical风格的回复（指令注入）"""
        persona = TechnicalAgent.persona_prompt()
        pricing = TechnicalAgent.pricing_strategy(
            base_price=context.get("base_price", 100) if context else 100,
            region_multiplier=context.get("region_multiplier", 1.0) if context else 1.0,
        )
        return (
            f"[AGENT: {TechnicalAgent.NAME} | STRATEGY: {TechnicalAgent.STRATEGY}]\n"
            f"{persona}\n\n"
            f"Pricing Strategy (Value Breakdown):\n{pricing['discount_note']}\n"
            f"Urgency: {pricing['urgency']}\n"
            "=== GENERATE YOUR REPLY BASED ON THE ABOVE ==="
        )
