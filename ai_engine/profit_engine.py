"""Profit Engine — 区域利润引擎

不同国家自动使用不同利润策略。

利润乘数：
  US → 1.0x (高利润 +$380-$600)
  EU → 0.95x (稳定利润 $300-$450)
  MEA → 1.6x (超高利润 $500-$900)
  APAC → 0.9x (中利润 $250-$400)
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class ProfitEngine:
    """区域利润引擎 — 自动利润策略"""

    # 国家基本利润配置
    COUNTRY_PROFILES = {
        "US": {
            "region": "NA",
            "base_multiplier": 1.0,
            "profit_range": (380, 600),
            "price_elasticity": "low",
            "strategy": "value_based",
            "note": "High margin — emphasize quality, warranty, speed",
        },
        "CA": {
            "region": "NA",
            "base_multiplier": 0.95,
            "profit_range": (350, 550),
            "price_elasticity": "low",
            "strategy": "value_based",
            "note": "Similar to US with slight adjustment for market size",
        },
        "GB": {
            "region": "EU",
            "base_multiplier": 0.95,
            "profit_range": (300, 450),
            "price_elasticity": "medium",
            "strategy": "quality_standard",
            "note": "Stable profit — focus on quality and compliance",
        },
        "DE": {
            "region": "EU",
            "base_multiplier": 0.95,
            "profit_range": (300, 450),
            "price_elasticity": "medium",
            "strategy": "quality_standard",
            "note": "Technical quality justifies price",
        },
        "FR": {
            "region": "EU",
            "base_multiplier": 0.95,
            "profit_range": (300, 450),
            "price_elasticity": "medium",
            "strategy": "quality_standard",
            "note": "Design and quality focus",
        },
        "AE": {
            "region": "MEA",
            "base_multiplier": 1.6,
            "profit_range": (500, 900),
            "price_elasticity": "very_low",
            "strategy": "luxury_premium",
            "note": "Ultra-high margin — luxury positioning, price signals quality",
        },
        "SA": {
            "region": "MEA",
            "base_multiplier": 1.5,
            "profit_range": (450, 800),
            "price_elasticity": "very_low",
            "strategy": "luxury_premium",
            "note": "High margin — prestige and quality focused",
        },
        "QA": {
            "region": "MEA",
            "base_multiplier": 1.6,
            "profit_range": (500, 900),
            "price_elasticity": "very_low",
            "strategy": "luxury_premium",
            "note": "Ultra-high margin — luxury market",
        },
        "AU": {
            "region": "APAC",
            "base_multiplier": 0.9,
            "profit_range": (250, 400),
            "price_elasticity": "medium",
            "strategy": "competitive_value",
            "note": "Mid profit — competitive market, good volume",
        },
        "SG": {
            "region": "APAC",
            "base_multiplier": 0.95,
            "profit_range": (280, 420),
            "price_elasticity": "medium",
            "strategy": "competitive_value",
            "note": "Slightly higher for Singapore premium positioning",
        },
        "JP": {
            "region": "APAC",
            "base_multiplier": 0.9,
            "profit_range": (280, 420),
            "price_elasticity": "medium",
            "strategy": "quality_value",
            "note": "Quality expectations justify moderate premium",
        },
    }

    # 默认区域利润配置
    REGION_DEFAULTS = {
        "NA": {"base_multiplier": 1.0, "profit_range": (350, 600), "strategy": "value_based"},
        "EU": {"base_multiplier": 0.95, "profit_range": (280, 450), "strategy": "quality_standard"},
        "MEA": {"base_multiplier": 1.6, "profit_range": (450, 900), "strategy": "luxury_premium"},
        "APAC": {"base_multiplier": 0.9, "profit_range": (250, 420), "strategy": "competitive_value"},
        "LATAM": {"base_multiplier": 0.85, "profit_range": (200, 350), "strategy": "market_penetration"},
    }

    @staticmethod
    def calculate_price(base_cost: float, country: str,
                        product_category: str = "general",
                        quantity: int = 1) -> dict:
        """根据国家和产品成本计算最终售价

        Args:
            base_cost: 基础成本
            country: 国家代码
            product_category: 产品类目
            quantity: 数量

        Returns:
            dict: {
                base_cost, country, region,
                profit_multiplier, profit_pct,
                selling_price, profit_amount,
                strategy, profit_range,
            }
        """
        country = country.upper() if country else "US"
        profile = ProfitEngine.COUNTRY_PROFILES.get(country)
        if not profile:
            # 回退到区域默认
            try:
                from global_router import GlobalRouter
                region = GlobalRouter.get_region_for_country(country)
                region_code = region.get("region", "APAC")
            except Exception:
                region_code = "APAC"
            region_default = ProfitEngine.REGION_DEFAULTS.get(region_code, ProfitEngine.REGION_DEFAULTS["APAC"])
            multiplier = region_default["base_multiplier"]
            profit_range = region_default["profit_range"]
            strategy = region_default["strategy"]
            region = region_code
        else:
            multiplier = profile["base_multiplier"]
            profit_range = profile["profit_range"]
            strategy = profile["strategy"]
            region = profile["region"]

        # 批量折扣
        volume_discount = 0
        if quantity >= 50:
            volume_discount = 0.08
        elif quantity >= 20:
            volume_discount = 0.05
        elif quantity >= 10:
            volume_discount = 0.03

        effective_multiplier = multiplier * (1 - volume_discount)
        selling_price = round(base_cost * effective_multiplier, 2)
        profit_amount = round(selling_price - base_cost, 2)
        profit_pct = round((profit_amount / base_cost) * 100, 1) if base_cost > 0 else 0

        return {
            "base_cost": round(base_cost, 2),
            "selling_price": selling_price,
            "profit_amount": profit_amount,
            "profit_pct": profit_pct,
            "country": country,
            "region": region,
            "profit_multiplier": effective_multiplier,
            "base_multiplier": multiplier,
            "strategy": strategy,
            "profit_range": list(profit_range),
            "quantity": quantity,
            "volume_discount_pct": volume_discount * 100,
        }

    @staticmethod
    def get_country_profile(country: str) -> dict:
        """获取国家利润配置"""
        country = country.upper()
        profile = ProfitEngine.COUNTRY_PROFILES.get(country)
        if profile:
            return profile
        # 回退
        try:
            from global_router import GlobalRouter
            region = GlobalRouter.get_region_for_country(country)
            region_code = region.get("region", "APAC")
        except Exception:
            region_code = "APAC"
        default = ProfitEngine.REGION_DEFAULTS.get(region_code, ProfitEngine.REGION_DEFAULTS["APAC"])
        return {
            "region": region_code,
            "base_multiplier": default["base_multiplier"],
            "profit_range": default["profit_range"],
            "strategy": default["strategy"],
        }

    @staticmethod
    def get_all_country_profiles() -> list:
        """获取所有国家利润配置"""
        return [
            {"country": c, **p}
            for c, p in ProfitEngine.COUNTRY_PROFILES.items()
        ]


# 快捷入口
engine = ProfitEngine()


def calculate_price(base_cost: float, country: str, **kwargs) -> dict:
    return ProfitEngine.calculate_price(base_cost, country, **kwargs)
