"""Brand Generator — 品牌自动生成

每个新公司自动生成：
  ✔ 品牌名
  ✔ Logo
  ✔ 网站
  ✔ 定位
  ✔ 话术
  ✔ 定价体系
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class BrandGenerator:
    """品牌生成器 — 为新公司自动生成完整品牌体系"""

    # 品牌命名风格
    NAMING_STYLES = {
        "modern": {
            "prefixes": ["Nova", "Viva", "Apex", "Luma", "Zeta", "Orbit", "Flux"],
            "suffixes": ["Works", "Studio", "Lab", "Group", "Pro", "Hub", "Craft"],
        },
        "luxury": {
            "prefixes": ["Royal", "Elite", "Prestige", "Crown", "Imperial", "Supreme"],
            "suffixes": ["Collection", "Exclusive", "Signature", "Luxury", "Premier"],
        },
        "professional": {
            "prefixes": ["Metro", "Urban", "City", "Core", "Prime", "Summit"],
            "suffixes": ["Solutions", "Services", "Systems", "Industries", "Partners"],
        },
        "local": {
            "prefixes": ["Local", "Neo", "Fresh", "Bright", "Quick"],
            "suffixes": ["Signs", "Design", "Works", "Shop", "Co"],
        },
    }

    # 行业→推荐命名风格
    INDUSTRY_STYLE = {
        "signage": ["modern", "professional", "local"],
        "luxury": ["luxury", "modern"],
        "technology": ["modern", "professional"],
        "furniture": ["modern", "luxury"],
        "lighting": ["modern", "professional"],
    }

    # 品牌颜色方案
    COLOR_PALETTES = {
        "modern": {"primary": "#2563EB", "secondary": "#7C3AED", "accent": "#06B6D4"},
        "luxury": {"primary": "#1A1A2E", "secondary": "#C5A55A", "accent": "#E94560"},
        "professional": {"primary": "#1E3A5F", "secondary": "#4A90D9", "accent": "#00B4D8"},
        "local": {"primary": "#FF6B35", "secondary": "#004E89", "accent": "#FFC857"},
    }

    @staticmethod
    def generate_brand(industry: str, market: str, style: str = "") -> dict:
        """为指定行业和市场生成品牌

        Args:
            industry: 行业
            market: 目标市场代码
            style: 风格 (modern/luxury/professional/local)，空=自动选择

        Returns:
            dict: {brand_name, tagline, positioning, voice, pricing}
        """
        # 选择风格
        if not style:
            preferred = BrandGenerator.INDUSTRY_STYLE.get(industry, ["modern"])
            style = preferred[0]

        # 生成品牌名
        brand_name = BrandGenerator._generate_name(style, industry, market)

        # 品牌定位
        positioning = BrandGenerator._generate_positioning(brand_name, industry, market, style)

        return {
            "brand_name": brand_name,
            "domain": f"{brand_name.lower().replace(' ', '')}.com",
            "industry": industry,
            "market": market,
            "style": style,
            "tagline": positioning["tagline"],
            "positioning": positioning["description"],
            "brand_voice": BrandGenerator._generate_voice(style),
            "color_palette": BrandGenerator.COLOR_PALETTES.get(style, BrandGenerator.COLOR_PALETTES["modern"]),
            "pricing_tier": BrandGenerator._get_pricing_tier(style, market),
            "target_audience": BrandGenerator._get_audience(industry, market),
        }

    @staticmethod
    def _generate_name(style: str, industry: str, market: str) -> str:
        """生成品牌名"""
        naming = BrandGenerator.NAMING_STYLES.get(style, BrandGenerator.NAMING_STYLES["modern"])
        import random
        prefix = random.choice(naming["prefixes"])
        suffix = random.choice(naming["suffixes"])

        market_hint = {"AE": "Dubai", "US": "America", "GB": "London", "AU": "Sydney"}
        hint = market_hint.get(market, "")

        if hint:
            return f"{prefix} {hint} {suffix}"
        return f"{prefix}{suffix}"

    @staticmethod
    def _generate_positioning(name: str, industry: str, market: str, style: str) -> dict:
        """生成品牌定位"""
        positions = {
            "modern": "Innovative, forward-thinking solutions for modern businesses",
            "luxury": "Premium, exclusive products for discerning clients",
            "professional": "Reliable, professional-grade solutions for serious businesses",
            "local": "Trusted local partner for quality business solutions",
        }
        taglines = {
            "modern": f"Illuminate Your Success",
            "luxury": f"Where Excellence Meets Design",
            "professional": f"Professional Grade, Trusted Results",
            "local": f"Your Local Partner in Quality",
        }
        return {
            "tagline": taglines.get(style, "Quality You Can Trust"),
            "description": positions.get(style, "Quality products for your business"),
        }

    @staticmethod
    def _generate_voice(style: str) -> dict:
        """生成品牌调性"""
        voices = {
            "modern": {"tone": "confident_innovative", "formality": "medium", "vocabulary": "contemporary"},
            "luxury": {"tone": "aspirational_exclusive", "formality": "high", "vocabulary": "sophisticated"},
            "professional": {"tone": "authoritative_trustworthy", "formality": "high", "vocabulary": "technical"},
            "local": {"tone": "friendly_approachable", "formality": "low", "vocabulary": "conversational"},
        }
        return voices.get(style, voices["professional"])

    @staticmethod
    def _get_pricing_tier(style: str, market: str) -> dict:
        """获取定价层级"""
        tier_map = {
            "luxury": "premium",
            "modern": "market_standard",
            "professional": "value_premium",
            "local": "competitive",
        }
        market_mult = {"AE": 1.5, "US": 1.0, "GB": 0.9, "AU": 0.85}
        mult = market_mult.get(market, 1.0)
        return {
            "tier": tier_map.get(style, "market_standard"),
            "market_multiplier": mult,
            "positioning": "price as quality signal" if style == "luxury" else "value based",
        }

    @staticmethod
    def _get_audience(industry: str, market: str) -> dict:
        """获取目标受众"""
        return {
            "primary": f"{industry.replace('_', ' ')} businesses in {market}",
            "secondary": "Business owners and decision makers",
            "pain_points": ["need visibility", "quality concerns", "competitive pressure"],
        }


# 快捷入口
generator = BrandGenerator()


def create_brand(industry: str, market: str, style: str = "") -> dict:
    return BrandGenerator.generate_brand(industry, market, style)
