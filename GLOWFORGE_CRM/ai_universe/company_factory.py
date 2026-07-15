"""Company Factory — 公司生成器（V8核心）

输入一个能力 → 输出多个公司

输入: luminous sign sales system
输出:
  Company A: US Restaurant Sign Business
  Company B: UAE Luxury Sign Business
  Company C: Hotel Interior Lighting System
  Company D: Acrylic Furniture Upsell Business

本质：一个系统 → 自动拆成多个盈利公司
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class CompanyFactory:
    """公司工厂 — 自动生成新公司"""

    # 公司模板
    COMPANY_TEMPLATES = {
        "signage": {
            "industry": "signage",
            "base_capability": "luminous_sign",
            "common_models": [
                {"name": "Quick Sign Co", "focus": "fast_production", "margin": "medium", "risk": "low"},
                {"name": "Premium Sign Studio", "focus": "luxury_design", "margin": "high", "risk": "low"},
                {"name": "Budget Signs Direct", "focus": "volume_low_cost", "margin": "low", "risk": "low"},
            ],
            "market_combinations": [
                {"market": "US", "focus": "restaurant", "profit_potential": 80},
                {"market": "AE", "focus": "luxury_retail", "profit_potential": 95},
                {"market": "GB", "focus": "pub_hotel", "profit_potential": 70},
                {"market": "AU", "focus": "cafe_retail", "profit_potential": 75},
            ],
        },
        "furniture": {
            "industry": "acrylic_furniture",
            "base_capability": "acrylic_display",
            "common_models": [
                {"name": "Modern Acrylic Designs", "focus": "contemporary", "margin": "high", "risk": "medium"},
                {"name": "Retail Display Pro", "focus": "commercial", "margin": "medium", "risk": "low"},
            ],
            "market_combinations": [
                {"market": "US", "focus": "retail_display", "profit_potential": 75},
                {"market": "AE", "focus": "luxury_interior", "profit_potential": 90},
            ],
        },
        "lighting": {
            "industry": "lighting_system",
            "base_capability": "led_lighting",
            "common_models": [
                {"name": "Architectural Lighting Co", "focus": "commercial", "margin": "high", "risk": "medium"},
                {"name": "GreenLED Solutions", "focus": "energy_efficient", "margin": "medium", "risk": "low"},
            ],
            "market_combinations": [
                {"market": "DE", "focus": "industrial", "profit_potential": 78},
                {"market": "AE", "focus": "hospitality", "profit_potential": 88},
            ],
        },
    }

    @staticmethod
    def generate_companies(base_capability: str, markets: list = None) -> dict:
        """从基础能力生成多个公司方案

        Args:
            base_capability: 基础能力 (luminous_sign, acrylic_furniture, led_lighting...)
            markets: 目标市场列表, None=自动选择

        Returns:
            dict: {companies: [...], total_companies, strategy}
        """
        template = CompanyFactory._find_template(base_capability)
        if not template:
            template = CompanyFactory.COMPANY_TEMPLATES["signage"]

        if markets is None:
            market_data = template.get("market_combinations", [])
        else:
            market_data = [
                m for m in template.get("market_combinations", [])
                if m["market"] in markets
            ] or template.get("market_combinations", [])[:2]

        companies = []
        for i, market in enumerate(market_data):
            model = template["common_models"][i % len(template["common_models"])]
            company = CompanyFactory._create_company(
                name=model["name"],
                focus=model["focus"],
                market=market["market"],
                industry=template["industry"],
                base_capability=base_capability,
                margin=model["margin"],
                risk=model["risk"],
                profit_potential=market["profit_potential"],
            )
            companies.append(company)

        return {
            "base_capability": base_capability,
            "industry": template["industry"],
            "total_companies": len(companies),
            "companies": companies,
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _find_template(capability: str) -> dict:
        """查找匹配的能力模板"""
        for tid, template in CompanyFactory.COMPANY_TEMPLATES.items():
            if capability.lower() in template["base_capability"] or capability.lower() in tid:
                return template
            # 检查扩展产品
            try:
                sys.path.insert(0, os.path.join(BASE_DIR, 'ai_engine'))
                from product_expander import ProductExpander
                expansion = ProductExpander.expand(capability)
                if expansion and not expansion.get("error"):
                    return template
            except Exception:
                pass
        return None

    @staticmethod
    def _create_company(name: str, focus: str, market: str, industry: str,
                        base_capability: str, margin: str, risk: str,
                        profit_potential: int) -> dict:
        """创建单个公司定义"""
        return {
            "company_name": f"{name} {market}",
            "legal_suffix": "LLC" if market in ("US", "AE") else "Ltd",
            "market": market,
            "industry": industry,
            "focus": focus,
            "base_capability": base_capability,
            "business_model": {
                "margin": margin,
                "risk": risk,
                "profit_potential": profit_potential,
                "estimated_monthly_revenue": CompanyFactory._estimate_revenue(market, margin),
            },
            "setup_requirements": {
                "website_needed": True,
                "whatsapp_needed": True,
                "social_media_needed": True,
                "estimated_setup_days": 14,
            },
            "strategic_positioning": CompanyFactory._generate_positioning(name, focus, market),
        }

    @staticmethod
    def _estimate_revenue(market: str, margin: str) -> dict:
        """估算月收入"""
        base_by_market = {"US": 15000, "AE": 25000, "GB": 12000, "AU": 10000, "DE": 14000, "SG": 18000}
        margin_mult = {"low": 0.7, "medium": 1.0, "high": 1.5}
        base = base_by_market.get(market, 10000)
        mult = margin_mult.get(margin, 1.0)
        return {
            "low": int(base * mult * 0.7),
            "expected": int(base * mult),
            "high": int(base * mult * 1.5),
        }

    @staticmethod
    def _generate_positioning(name: str, focus: str, market: str) -> str:
        """生成战略定位描述"""
        return (
            f"{name} focuses on {focus.replace('_', ' ')} in the {market} market, "
            f"leveraging Bohui GLOWFORGE's manufacturing capabilities "
            f"to deliver premium products with local market adaptation."
        )


# 快捷入口
factory = CompanyFactory()


def generate(base_capability: str, markets: list = None) -> dict:
    return CompanyFactory.generate_companies(base_capability, markets)
