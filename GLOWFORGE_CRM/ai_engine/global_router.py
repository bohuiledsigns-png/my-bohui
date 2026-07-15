"""Global Router — 全球路由系统

客户来源国家 → 区域路由 + 策略匹配

核心映射：
  NA (US/CA)    → high_margin_fast_close
  EU (UK/DE/FR) → professional_stable
  MEA (AE/SA)   → luxury_premium
  APAC (AU/SG)  → mid_price_efficient
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class GlobalRouter:
    """全球路由系统 — 国家→区域分流"""

    # 区域定义
    REGIONS = {
        "NA": {
            "code": "NA",
            "name": "North America",
            "countries": ["US", "CA"],
            "sales_strategy": "high_margin_fast_close",
            "agent_pool": ["hunter_agent", "closer_agent"],
            "pricing_mode": "premium_anchor",
            "currency": "USD",
            "culture_profile": "direct_results",
        },
        "EU": {
            "code": "EU",
            "name": "Europe",
            "countries": ["GB", "UK", "DE", "FR", "IT", "ES", "NL"],
            "sales_strategy": "professional_stable",
            "agent_pool": ["consultant_agent", "technical_agent"],
            "pricing_mode": "quality_standard",
            "currency": "EUR",
            "culture_profile": "formal_technical",
        },
        "MEA": {
            "code": "MEA",
            "name": "Middle East & Africa",
            "countries": ["AE", "SA", "QA", "KW", "OM", "BH", "ZA"],
            "sales_strategy": "luxury_premium",
            "agent_pool": ["closer_agent", "hunter_agent"],
            "pricing_mode": "luxury_markup",
            "currency": "AED",
            "culture_profile": "luxury_visual",
        },
        "APAC": {
            "code": "APAC",
            "name": "Asia Pacific",
            "countries": ["AU", "SG", "MY", "TH", "VN", "PH", "NZ", "JP", "KR"],
            "sales_strategy": "mid_price_efficient",
            "agent_pool": ["consultant_agent", "soft_seller_agent"],
            "pricing_mode": "competitive_value",
            "currency": "USD",
            "culture_profile": "relationship_first",
        },
        "LATAM": {
            "code": "LATAM",
            "name": "Latin America",
            "countries": ["BR", "MX", "AR", "CL", "CO", "PE"],
            "sales_strategy": "growth_market",
            "agent_pool": ["hunter_agent", "soft_seller_agent"],
            "pricing_mode": "market_penetration",
            "currency": "USD",
            "culture_profile": "warm_relationship",
        },
    }

    # 国家→区域快速映射
    COUNTRY_TO_REGION = {}
    for region_code, region_data in REGIONS.items():
        for country in region_data["countries"]:
            COUNTRY_TO_REGION[country] = region_code

    @staticmethod
    def route(country: str, intent: str = "", product: str = "",
              urgency: str = "medium") -> dict:
        """路由客户到区域策略

        Args:
            country: ISO国家代码 (US, AE, DE...)
            intent: BUDGET / QUALITY / URGENT / GENERAL
            product: 产品类目
            urgency: high / medium / low

        Returns:
            dict: {
                region, sales_strategy, agent_pool, pricing_mode,
                currency, culture_profile, region_name
            }
        """
        country = country.upper() if country else ""
        region_code = GlobalRouter.COUNTRY_TO_REGION.get(country, "APAC")
        region = GlobalRouter.REGIONS.get(region_code, GlobalRouter.REGIONS["APAC"])

        return {
            "region": region_code,
            "region_name": region["name"],
            "sales_strategy": region["sales_strategy"],
            "agent_pool": list(region["agent_pool"]),
            "pricing_mode": region["pricing_mode"],
            "currency": region["currency"],
            "culture_profile": region["culture_profile"],
            "country": country,
        }

    @staticmethod
    def get_region_for_country(country: str) -> dict:
        """获取国家对应的区域信息"""
        return GlobalRouter.route(country)

    @staticmethod
    def get_all_regions() -> list:
        """获取所有区域配置"""
        return [
            {
                "code": r["code"],
                "name": r["name"],
                "countries": r["countries"],
                "sales_strategy": r["sales_strategy"],
                "pricing_mode": r["pricing_mode"],
                "currency": r["currency"],
            }
            for r in GlobalRouter.REGIONS.values()
        ]


# 快捷入口
router = GlobalRouter()


def route_country(country: str, intent: str = "") -> dict:
    return GlobalRouter.route(country, intent)
