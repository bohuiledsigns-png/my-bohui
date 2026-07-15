"""Discount Policy — 上下文感知折扣规则

根据客户等级、市场、产品类型制定差异化折扣策略。
"""
import logging

logger = logging.getLogger("discount_policy")

TIER_DISCOUNT_LIMITS = {
    "LOW": 0.05,
    "MEDIUM": 0.10,
    "HIGH_VALUE": 0.15,
    "VIP": 0.20,
}

MARKET_DISCOUNT_FACTORS = {
    "US": 0.8, "CA": 0.85,
    "GB": 0.8, "DE": 0.8, "FR": 0.85, "IT": 0.9, "ES": 0.9, "NL": 0.85,
    "AE": 0.7, "SA": 0.75, "QA": 0.7, "KW": 0.75, "OM": 0.8, "BH": 0.8,
    "AU": 0.85, "SG": 0.85, "JP": 0.7, "MY": 1.0,
}


class DiscountPolicy:
    """折扣策略引擎"""

    @staticmethod
    def generate_policy(country_code=None, customer_tier="LOW"):
        """生成折扣策略"""
        tier_limit = TIER_DISCOUNT_LIMITS.get(customer_tier, 0.05)
        market_factor = MARKET_DISCOUNT_FACTORS.get(country_code, 1.0) if country_code else 1.0

        max_discount = round(tier_limit * market_factor, 4)
        recommended = round(max_discount * 0.7, 4)

        warnings = []
        if max_discount > 0.25:
            warnings.append("折扣超过商业宪法25%上限，已被限制")
            max_discount = 0.25
            recommended = 0.175

        return {
            "country": country_code,
            "customer_tier": customer_tier,
            "max_discount_pct": max_discount,
            "recommended_discount_pct": recommended,
            "policy_rules": {
                "single_use_per_customer": True,
                "cooldown_days": 30,
                "requires_approval_above": 0.15,
            },
            "warnings": warnings,
        }

    @staticmethod
    def get_max_discount(customer_tier, country_code=None):
        policy = DiscountPolicy.generate_policy(
            country_code=country_code, customer_tier=customer_tier
        )
        return policy["max_discount_pct"]

    @staticmethod
    def validate_discount(discount_pct, customer_tier, country_code=None):
        """验证折扣是否合规"""
        max_allowed = DiscountPolicy.get_max_discount(customer_tier, country_code)
        allowed = discount_pct <= max_allowed and discount_pct <= 0.25

        return {
            "allowed": allowed,
            "discount_requested": discount_pct,
            "max_allowed": max_allowed,
            "reason": "ok" if allowed else f"折扣 {discount_pct:.0%} 超过上限 {max_allowed:.0%}",
        }
