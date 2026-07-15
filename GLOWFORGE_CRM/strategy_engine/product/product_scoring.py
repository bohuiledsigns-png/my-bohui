"""Product Scoring — V3 产品评分引擎

从利润角度评估每个产品的战略价值，回答「卖什么最赚钱」。
"""
import logging
from datetime import datetime

from strategy_engine.db import _read_db, parse_items

logger = logging.getLogger("product_scoring")

SCORE_WEIGHTS = {
    "revenue_contribution": 0.30,
    "margin_percentage": 0.25,
    "sales_volume": 0.20,
    "growth_trend": 0.15,
    "order_frequency": 0.10,
}


class ProductScoring:
    """V3 产品评分引擎"""

    @staticmethod
    def score_products(dry_run=True):
        """对所有产品执行综合评分"""
        products = ProductScoring._load_product_data()

        scored = []
        for p in products:
            dimensions = ProductScoring._calculate_dimensions(p)
            total_score = sum(
                dimensions.get(key, 0) * weight
                for key, weight in SCORE_WEIGHTS.items()
            )

            scored.append({
                "product_name": p["name"],
                "total_revenue": p["revenue"],
                "total_orders": p["orders"],
                "total_units": p["units"],
                "avg_price": p.get("avg_price", 0),
                "product_score": round(total_score, 2),
                "dimensions": dimensions,
                "recommendation": ProductScoring._classify(total_score),
            })

        scored.sort(key=lambda x: x["product_score"], reverse=True)
        return scored

    @staticmethod
    def _load_product_data():
        """从订单 items JSON 加载产品数据"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT items, total_amount, created_at
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND items != '[]' AND items IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 500
            """).fetchall()
        except Exception as e:
            logger.warning(f"Load product data error: {e}")
            return []
        finally:
            conn.close()

        product_stats = {}
        now = datetime.now().isoformat()

        for r in rows:
            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                qty = item.get("quantity", item.get("qty", 1)) or 1
                price = item.get("price", item.get("unit_price", 0)) or 0

                if name not in product_stats:
                    product_stats[name] = {
                        "revenue": 0, "orders": 0, "units": 0,
                        "first_seen": now, "last_seen": None,
                    }
                product_stats[name]["revenue"] += price * qty
                product_stats[name]["orders"] += 1
                product_stats[name]["units"] += qty
                created = r["created_at"] if "created_at" in r else ""
                if created:
                    if not product_stats[name]["first_seen"] or created < product_stats[name]["first_seen"]:
                        product_stats[name]["first_seen"] = created
                    if not product_stats[name]["last_seen"] or created > product_stats[name]["last_seen"]:
                        product_stats[name]["last_seen"] = created

        result = []
        for name, stats in product_stats.items():
            days_active = 90
            if stats["first_seen"] and stats["last_seen"]:
                try:
                    start = datetime.strptime(stats["first_seen"][:19], "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(stats["last_seen"][:19], "%Y-%m-%d %H:%M:%S")
                    days_active = max(1, (end - start).days)
                except (ValueError, TypeError):
                    pass

            result.append({
                "name": name,
                "revenue": stats["revenue"],
                "orders": stats["orders"],
                "units": stats["units"],
                "avg_price": round(stats["revenue"] / stats["units"], 2) if stats["units"] > 0 else 0,
                "frequency": round(stats["orders"] / days_active, 4),
            })

        return result

    @staticmethod
    def _calculate_dimensions(product):
        revenue = product.get("revenue", 0)
        units = product.get("units", 0)

        return {
            "revenue_contribution": min(100, revenue / 100000 * 100),
            "margin_percentage": 50,
            "sales_volume": min(100, units / 200 * 100),
            "growth_trend": 50,
            "order_frequency": min(100, product.get("frequency", 0) * 1000),
        }

    @staticmethod
    def _classify(score):
        if score >= 70:
            return "star"
        elif score >= 50:
            return "growth"
        elif score >= 30:
            return "sustain"
        return "review"

    @staticmethod
    def get_top_products(n=5, dry_run=True):
        scored = ProductScoring.score_products(dry_run=dry_run)
        return scored[:n]

    @staticmethod
    def get_product_recommendation(product_name, dry_run=True):
        scored = ProductScoring.score_products(dry_run=dry_run)
        for p in scored:
            if p["product_name"] == product_name:
                return p
        return {"error": f"Product '{product_name}' not found"}
