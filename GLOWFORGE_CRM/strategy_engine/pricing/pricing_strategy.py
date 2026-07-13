"""Pricing Strategy — 跨市场×产品定价策略

为每个产品在每个市场制定最优定价策略。
基于成本加成 + 市场系数定价模型。
"""
import logging

from strategy_engine.db import _read_db

logger = logging.getLogger("pricing_strategy")

MARKET_PRICE_FACTORS = {
    "US": 1.2, "CA": 1.15,
    "GB": 1.25, "DE": 1.2, "FR": 1.15, "IT": 1.1, "ES": 1.1, "NL": 1.15,
    "AE": 1.3, "SA": 1.25, "QA": 1.35, "KW": 1.3, "OM": 1.2, "BH": 1.25,
    "AU": 1.2, "SG": 1.15, "JP": 1.3, "MY": 1.0,
}

TARGET_MARGINS = {
    "star": 0.45,
    "growth": 0.40,
    "sustain": 0.35,
    "review": 0.30,
}


class PricingStrategy:
    """定价策略引擎"""

    @staticmethod
    def develop_strategy(dry_run=True):
        """制定完整定价策略"""
        conn = _read_db()
        try:
            cost_row = conn.execute("""
                SELECT COALESCE(AVG(base_cost), 0) as avg_cost
                FROM production_costs
            """).fetchone()
        except Exception:
            cost_row = {"avg_cost": 100}
        finally:
            conn.close()

        base_cost = cost_row["avg_cost"] if cost_row else 100

        markets = []
        try:
            from strategy_engine.market.market_scoring import MarketScoring
            markets = MarketScoring.score_markets(dry_run=dry_run)
        except Exception as e:
            logger.warning(f"MarketScoring unavailable for pricing: {e}")

        products = []
        try:
            from strategy_engine.product.product_scoring import ProductScoring
            products = ProductScoring.score_products(dry_run=dry_run)
        except Exception as e:
            logger.warning(f"ProductScoring unavailable for pricing: {e}")

        strategies = []
        for m in markets[:5]:
            cc = m["country_code"]
            price_factor = MARKET_PRICE_FACTORS.get(cc, 1.0)

            for p in products[:3]:
                rec = p.get("recommendation", "sustain")
                target_margin = TARGET_MARGINS.get(rec, 0.35)

                base_price = base_cost / (1 - target_margin)
                market_price = base_price * price_factor

                strategies.append({
                    "country": cc,
                    "product": p["product_name"],
                    "base_cost": round(base_cost, 2),
                    "base_price": round(base_price, 2),
                    "market_price": round(market_price, 2),
                    "target_margin": target_margin,
                    "price_factor": price_factor,
                    "product_recommendation": rec,
                    "market_recommendation": m.get("recommendation", "hold"),
                })

        strategies.sort(key=lambda x: x["market_price"], reverse=True)

        return {
            "strategies": strategies,
            "overall": {
                "avg_target_margin": round(
                    sum(s["target_margin"] for s in strategies) / max(len(strategies), 1), 4
                ),
                "market_count": len(markets),
                "product_count": len(products),
                "strategy_count": len(strategies),
            },
        }

    @staticmethod
    def get_optimal_margin(country_code, product_category=None):
        """获取特定市场的最优利润率"""
        factor = MARKET_PRICE_FACTORS.get(country_code, 1.0)

        if factor >= 1.25:
            base_margin = 0.45
        elif factor >= 1.1:
            base_margin = 0.40
        else:
            base_margin = 0.35

        return {
            "country": country_code,
            "price_factor": factor,
            "recommended_margin": base_margin,
            "min_acceptable_margin": 0.25,
            "margin_range": [0.25, base_margin + 0.10],
        }

    @staticmethod
    def recommend_tier(country_code, product_category=None):
        """为特定市场推荐定价层级"""
        factor = MARKET_PRICE_FACTORS.get(country_code, 1.0)

        if factor >= 1.3:
            tier = "premium"
        elif factor >= 1.15:
            tier = "standard"
        else:
            tier = "economy"

        return {
            "country": country_code,
            "price_tier": tier,
            "price_factor": factor,
            "description": {
                "premium": "高端定价，最大化单笔利润",
                "standard": "标准定价，平衡销量和利润",
                "economy": "经济定价，以量取胜",
            }.get(tier, "standard"),
        }
