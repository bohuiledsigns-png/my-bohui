"""Market Scoring — V3 市场评分引擎

整合 V2 Geo Score + V3 实际数据（营收/转化/增长），
输出每个市场的综合评分和推荐策略。
"""
import logging

from strategy_engine.db import _read_db, normalize_country

logger = logging.getLogger("market_scoring")

SCORE_WEIGHTS = {
    "revenue_potential": 0.25,
    "conversion_efficiency": 0.20,
    "growth_trend": 0.15,
    "avg_order_value": 0.15,
    "product_market_fit": 0.15,
    "geo_score": 0.10,
}


class MarketScoring:
    """V3 市场评分引擎"""

    @staticmethod
    def score_markets(dry_run=True):
        """对所有目标市场执行综合评分"""
        market_data = MarketScoring._load_market_data()

        v2_scores = {}
        try:
            from ai_overlay.v2_market_expansion import MarketExpansionEngine
            v2_results = MarketExpansionEngine.score_all_markets(use_db=False)
            for m in v2_results:
                v2_scores[m["country_code"]] = m.get("geo_score", 0)
        except Exception as e:
            logger.warning(f"V2 MarketExpansionEngine unavailable: {e}")

        scored = []
        for row in market_data:
            cc = row["country_code"]
            v2_score = v2_scores.get(cc, 50)

            dimensions = MarketScoring._calculate_dimensions(row, v2_score)
            v3_score = sum(
                dimensions.get(key, 0) * weight
                for key, weight in SCORE_WEIGHTS.items()
            )

            scored.append({
                "country_code": cc,
                "country_name": row.get("country_name", cc),
                "region": row.get("region", "unknown"),
                "v3_score": round(v3_score, 2),
                "v2_geo_score": round(v2_score, 2),
                "dimensions": dimensions,
                "revenue": row.get("revenue", 0),
                "orders": row.get("orders", 0),
                "customers": row.get("customers", 0),
                "conversion_rate": row.get("conversion_rate", 0),
                "recommendation": MarketScoring._classify_score(v3_score),
            })

        scored.sort(key=lambda x: x["v3_score"], reverse=True)
        return scored

    @staticmethod
    def _load_market_data():
        """从 DB 加载各市场指标"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    c.country AS raw_country,
                    COUNT(DISTINCT c.id) AS customers,
                    COUNT(DISTINCT o.id) AS orders,
                    COALESCE(SUM(o.total_amount), 0) AS revenue,
                    COALESCE(AVG(o.total_amount), 0) AS avg_order_value,
                    COUNT(DISTINCT m.id) AS messages
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                LEFT JOIN messages m ON m.customer_id = c.id
                WHERE c.country != '' AND c.country IS NOT NULL
                GROUP BY c.country
                ORDER BY revenue DESC
            """).fetchall()
        except Exception as e:
            logger.warning(f"Load market data error: {e}")
            return []
        finally:
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["country_code"] = normalize_country(d.pop("raw_country"))
            d["region"] = MarketScoring._get_region(d["country_code"])
            d["conversion_rate"] = MarketScoring._calc_conversion_rate(d["country_code"])
            result.append(d)
        return result

    @staticmethod
    def _calc_conversion_rate(country_code):
        """计算指定市场的转化率"""
        conn = _read_db()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won
                FROM v3_conversions v
                JOIN customers c ON c.id = v.customer_id
                WHERE c.country = ? AND v.final_result IN ('won', 'lost')
            """, (country_code,)).fetchone()
            if row and row["total"] > 0:
                return round(row["won"] / row["total"] * 100, 2)
        except Exception:
            pass
        finally:
            conn.close()
        return 0

    @staticmethod
    def _get_region(country_code):
        cc = normalize_country(country_code)
        region_map = {
            "US": "NA", "CA": "NA",
            "GB": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU", "NL": "EU",
            "AE": "MEA", "SA": "MEA", "QA": "MEA", "KW": "MEA", "OM": "MEA", "BH": "MEA",
            "AU": "APAC", "SG": "APAC", "JP": "APAC", "MY": "APAC",
        }
        return region_map.get(cc, "OTHER")

    @staticmethod
    def _calculate_dimensions(row, v2_score):
        revenue = row.get("revenue", 0) or 0
        orders = row.get("orders", 0) or 0
        customers = row.get("customers", 0) or 0
        aov = row.get("avg_order_value", 0) or 0
        conv_rate = row.get("conversion_rate", 0) or 0

        return {
            "revenue_potential": min(100, revenue / 10000 * 100) if revenue > 0 else 0,
            "conversion_efficiency": min(100, conv_rate * 5),
            "growth_trend": 50,
            "avg_order_value": min(100, aov / 200 * 100) if aov > 0 else 0,
            "product_market_fit": min(100, orders / max(customers, 1) * 50),
            "geo_score": v2_score,
        }

    @staticmethod
    def _classify_score(score):
        if score >= 75:
            return "strong_buy"
        elif score >= 55:
            return "buy"
        elif score >= 35:
            return "hold"
        return "weak"

    @staticmethod
    def get_top_markets(n=5, dry_run=True):
        scored = MarketScoring.score_markets(dry_run=dry_run)
        return scored[:n]

    @staticmethod
    def get_market_recommendation(country_code, dry_run=True):
        scored = MarketScoring.score_markets(dry_run=dry_run)
        for m in scored:
            if m["country_code"] == country_code:
                return m
        return {"error": f"Market {country_code} not found"}
