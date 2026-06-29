"""Demand Fit — 产品×市场匹配矩阵

分析每个产品在每个市场的表现，找出最佳产品-市场组合（PMF）。
"""
import logging

from strategy_engine.db import _read_db, parse_items, normalize_country

logger = logging.getLogger("demand_fit")


class DemandFit:
    """产品×市场匹配分析引擎"""

    @staticmethod
    def analyze_product_market_fit():
        """构建产品×市场匹配矩阵"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT c.country, o.items, o.total_amount
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND o.items != '[]' AND o.items IS NOT NULL
                  AND c.country != '' AND c.country IS NOT NULL
                ORDER BY o.created_at DESC
                LIMIT 500
            """).fetchall()
        except Exception as e:
            logger.warning(f"Product-market fit error: {e}")
            return []
        finally:
            conn.close()

        matrix = {}
        for r in rows:
            country = normalize_country(r["country"])
            if country not in matrix:
                matrix[country] = {}

            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                qty = item.get("quantity", item.get("qty", 1)) or 1
                price = item.get("price", item.get("unit_price", 0)) or 0

                if name not in matrix[country]:
                    matrix[country][name] = {"revenue": 0, "orders": 0, "total_qty": 0}

                matrix[country][name]["revenue"] += price * qty
                matrix[country][name]["orders"] += 1
                matrix[country][name]["total_qty"] += qty

        results = []
        for country, products in matrix.items():
            for product, stats in products.items():
                aov = round(stats["revenue"] / stats["orders"], 2) if stats["orders"] > 0 else 0

                revenue_score = min(100, stats["revenue"] / 5000 * 100)
                order_score = min(100, stats["orders"] / 10 * 100)
                aov_score = min(100, aov / 500 * 100)

                fit_score = round(
                    revenue_score * 0.4 + order_score * 0.35 + aov_score * 0.25, 2
                )

                results.append({
                    "country": country,
                    "product_category": product,
                    "revenue": round(stats["revenue"], 2),
                    "orders": stats["orders"],
                    "avg_order_value": aov,
                    "fit_score": fit_score,
                    "opportunity_rating": DemandFit._rate_opportunity(fit_score),
                })

        results.sort(key=lambda x: x["fit_score"], reverse=True)
        return results

    @staticmethod
    def _rate_opportunity(score):
        if score >= 60:
            return "high"
        elif score >= 30:
            return "medium"
        elif score >= 10:
            return "low"
        return "minimal"

    @staticmethod
    def get_recommended_combinations(min_score=30):
        matrix = DemandFit.analyze_product_market_fit()
        return [m for m in matrix if m["fit_score"] >= min_score]

    @staticmethod
    def get_gap_analysis():
        """识别有客户但未成交的高潜力产品×市场组合"""
        conn = _read_db()
        try:
            countries = conn.execute("""
                SELECT DISTINCT country FROM customers
                WHERE country != '' AND country IS NOT NULL
            """).fetchall()

            products = conn.execute("""
                SELECT DISTINCT o.items
                FROM orders o
                WHERE o.status IN ('shipped', 'delivered', 'completed')
                  AND o.items != '[]' AND o.items IS NOT NULL
                LIMIT 100
            """).fetchall()
        except Exception as e:
            logger.warning(f"Gap analysis error: {e}")
            return []
        finally:
            conn.close()

        all_products = set()
        for r in products:
            try:
                items = json.loads(r["items"])
                if isinstance(items, list):
                    for item in items:
                        name = item.get("name", item.get("product", "unknown"))
                        all_products.add(name)
            except (json.JSONDecodeError, TypeError):
                continue

        existing = DemandFit.analyze_product_market_fit()
        existing_pairs = {(m["country"], m["product_category"]) for m in existing}

        gaps = []
        for c in countries:
            cc = c["country"]
            for p in all_products:
                if (cc, p) not in existing_pairs:
                    gaps.append({
                        "country": cc,
                        "product_category": p,
                        "status": "no_orders",
                        "potential": "unknown",
                    })

        return gaps
