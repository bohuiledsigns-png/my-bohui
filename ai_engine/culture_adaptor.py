"""Culture Adaptor — 文化话术适配器

同一产品 → 不同国家完全不同的表达方式。
不是翻译，是"心理产品的重新构建"。

国家文化画像：
  US: 直接+结果导向 → "walk-in traffic, storefront visibility"
  DE: 理性+技术 → "1.0mm stainless steel, certified LED modules"
  AE: 高端+视觉冲击 → "luxury illuminated, premium brand presence"
  JP: 礼貌+细节 → "precision craftsmanship, harmonious design"
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class CultureAdaptor:
    """文化话术适配器 — 国家文化语言映射"""

    # 国家→文化风格映射
    CULTURE_STYLES = {
        "US": {
            "code": "US",
            "style": "direct_results",
            "tone": "confident_direct",
            "keywords": ["ROI", "traffic", "visibility", "sales boost", "competitive edge"],
            "formality": "low",
            "emotional_appeal": "ambition_success",
            "decision_style": "fast_decisive",
            "greeting": "Hi",
            "signature": "Best regards",
        },
        "CA": {
            "code": "CA",
            "style": "friendly_professional",
            "tone": "polite_confident",
            "keywords": ["value", "quality", "service", "reliability"],
            "formality": "low",
            "emotional_appeal": "trust_reliability",
            "decision_style": "balanced",
            "greeting": "Hello",
            "signature": "Best regards",
        },
        "GB": {
            "code": "GB",
            "style": "polish_professional",
            "tone": "formal_polite",
            "keywords": ["quality", "craftsmanship", "heritage", "premium", "bespoke"],
            "formality": "high",
            "emotional_appeal": "tradition_prestige",
            "decision_style": "considered",
            "greeting": "Dear",
            "signature": "Yours faithfully",
        },
        "DE": {
            "code": "DE",
            "style": "technical_precision",
            "tone": "direct_formal",
            "keywords": ["precision", "engineering", "certified", "durable", "specification"],
            "formality": "high",
            "emotional_appeal": "efficiency_reliability",
            "decision_style": "thorough_analytical",
            "greeting": "Guten Tag",
            "signature": "Mit freundlichen Grüßen",
        },
        "FR": {
            "code": "FR",
            "style": "elegant_refined",
            "tone": "polite_artistic",
            "keywords": ["design", "elegance", "quality", "style", "savoir-faire"],
            "formality": "high",
            "emotional_appeal": "aesthetics_beauty",
            "decision_style": "considered",
            "greeting": "Bonjour",
            "signature": "Cordialement",
        },
        "AE": {
            "code": "AE",
            "style": "luxury_prestige",
            "tone": "formal_aspirational",
            "keywords": ["luxury", "premium", "exclusive", "magnificent", "royal"],
            "formality": "high",
            "emotional_appeal": "status_prestige",
            "decision_style": "relationship_first",
            "greeting": "Dear",
            "signature": "Best regards",
        },
        "SA": {
            "code": "SA",
            "style": "luxury_traditional",
            "tone": "formal_respectful",
            "keywords": ["premium", "quality", "excellence", "trusted", "distinguished"],
            "formality": "very_high",
            "emotional_appeal": "honor_reputation",
            "decision_style": "relationship_long_term",
            "greeting": "Dear",
            "signature": "Best regards",
        },
        "JP": {
            "code": "JP",
            "style": "polite_detailed",
            "tone": "very_formal_humble",
            "keywords": ["precision", "craftsmanship", "quality", "reliable", "trustworthy"],
            "formality": "very_high",
            "emotional_appeal": "harmony_trust",
            "decision_style": "slow_consensus",
            "greeting": "様",
            "signature": "敬具",
        },
        "AU": {
            "code": "AU",
            "style": "friendly_casual",
            "tone": "casual_direct",
            "keywords": ["great value", "solid quality", "no worries", "fair dinkum"],
            "formality": "low",
            "emotional_appeal": "practicality_fairness",
            "decision_style": "fast_practical",
            "greeting": "G'day",
            "signature": "Cheers",
        },
        "SG": {
            "code": "SG",
            "style": "efficient_professional",
            "tone": "polite_direct",
            "keywords": ["efficient", "cost-effective", "quality", "reliable", "fast delivery"],
            "formality": "medium",
            "emotional_appeal": "efficiency_value",
            "decision_style": "fast_pragmatic",
            "greeting": "Hello",
            "signature": "Best regards",
        },
    }

    # 产品特征→不同国家不同表达重点
    PRODUCT_ANGLES = {
        "luminous_sign": {
            "US": "Increase foot traffic and stand out from competitors",
            "DE": "Engineered with certified LED modules for 50,000-hour operation",
            "AE": "Luxury illuminated signage for premium brand presence",
            "JP": "Precision-crafted illumination with harmonious design integration",
            "default": "High-quality luminous signage for your business",
        },
        "led_display": {
            "US": "Boost sales with dynamic digital advertising",
            "DE": "Industrial-grade LED display with precise color calibration",
            "AE": "Spectacular visual impact for prestigious locations",
            "default": "Professional LED display solution",
        },
    }

    @staticmethod
    def adapt(product_description: str, country: str, product_type: str = "") -> str:
        """将产品描述适配到目标国家的文化表达

        Args:
            product_description: 原始产品描述
            country: 目标国家代码
            product_type: 产品类型（可选）

        Returns:
            str: 文化适配后的产品描述
        """
        country = country.upper()
        style = CultureAdaptor.CULTURE_STYLES.get(country, {})
        if not style:
            return product_description

        # 检查是否有预设的产品角度
        if product_type:
            angles = CultureAdaptor.PRODUCT_ANGLES.get(product_type, {})
            adapted = angles.get(country) or angles.get("default", "")
            if adapted:
                return adapted

        # 基于风格的通用适配
        keywords = style.get("keywords", [])
        keyword_hint = ", ".join(keywords[:3]) if keywords else ""

        return (
            f"[CULTURE ADAPTED for {country} — Style: {style.get('style', 'standard')}]\n"
            f"Tone: {style.get('tone', 'professional')}\n"
            f"Key concepts to emphasize: {keyword_hint}\n"
            f"Decision style: {style.get('decision_style', 'standard')}\n"
            f"Original description: {product_description}\n"
            f"Adapt this description naturally for a {country} audience."
        )

    @staticmethod
    def get_culture_context(country: str) -> dict:
        """获取国家的文化上下文（供Agent prompt注入）

        Args:
            country: 国家代码

        Returns:
            dict: 文化配置
        """
        country = country.upper()
        style = CultureAdaptor.CULTURE_STYLES.get(country, {})
        if not style:
            return {
                "country": country,
                "style": "standard",
                "tone": "professional",
                "keywords": [],
                "formality": "medium",
            }

        return {
            "country": country,
            "country_name": CultureAdaptor.get_country_name(country),
            "style": style.get("style", "standard"),
            "tone": style.get("tone", "professional"),
            "keywords": style.get("keywords", []),
            "formality": style.get("formality", "medium"),
            "emotional_appeal": style.get("emotional_appeal", ""),
            "decision_style": style.get("decision_style", "standard"),
            "greeting": style.get("greeting", "Hello"),
            "signature": style.get("signature", "Best regards"),
        }

    @staticmethod
    def get_country_name(code: str) -> str:
        """国家代码→中文/英文名称"""
        names = {
            "US": "United States", "CA": "Canada",
            "GB": "United Kingdom", "UK": "United Kingdom",
            "DE": "Germany", "FR": "France",
            "IT": "Italy", "ES": "Spain", "NL": "Netherlands",
            "AE": "UAE", "SA": "Saudi Arabia",
            "QA": "Qatar", "KW": "Kuwait",
            "JP": "Japan", "AU": "Australia",
            "SG": "Singapore", "MY": "Malaysia",
            "BR": "Brazil", "MX": "Mexico",
        }
        return names.get(code.upper(), code)


# 快捷入口
adaptor = CultureAdaptor()


def adapt_message(text: str, country: str, product_type: str = "") -> str:
    return CultureAdaptor.adapt(text, country, product_type)


def get_culture_context(country: str) -> dict:
    return CultureAdaptor.get_culture_context(country)
