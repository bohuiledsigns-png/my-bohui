"""Demand Analyzer — 市场需求分析

分析产品需求趋势、季节性模式、品类热度变化。
"""
import logging

from strategy_engine.db import _read_db, parse_items

logger = logging.getLogger("demand_analyzer")


class DemandAnalyzer:
    """市场需求分析引擎"""

    @staticmethod
    def analyze_demand_trends(days=180):
        """分析近期需求趋势"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    strftime('%Y-%m', created_at) as month,
                    COUNT(*) as orders,
                    COALESCE(SUM(total_amount), 0) as revenue,
                    COUNT(DISTINCT customer_id) as unique_customers
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND created_at >= datetime('now', ? || ' days')
                GROUP BY strftime('%Y-%m', created_at)
                ORDER BY month
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Demand trends error: {e}")
            return {"overall_trend": "unknown", "monthly_breakdown": []}
        finally:
            conn.close()

        monthly = [dict(r) for r in rows]
        trend = DemandAnalyzer._calc_trend(monthly)
        cat_trends = DemandAnalyzer._analyze_category_trends(days)

        return {
            "overall_trend": trend,
            "monthly_breakdown": monthly,
            "category_trends": cat_trends,
            "analysis_period_days": days,
        }

    @staticmethod
    def _calc_trend(monthly):
        if len(monthly) < 2:
            return "insufficient_data"

        recent = monthly[-1].get("revenue", 0)
        previous = monthly[-2].get("revenue", 0)

        if previous == 0:
            return "growing" if recent > 0 else "stable"

        change = (recent - previous) / previous
        if change > 0.15:
            return "growing"
        elif change < -0.15:
            return "declining"
        return "stable"

    @staticmethod
    def _analyze_category_trends(days):
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT o.items, o.total_amount
                FROM orders o
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND o.items != '[]' AND o.items IS NOT NULL
                  AND o.created_at >= datetime('now', ? || ' days')
                ORDER BY o.created_at DESC
                LIMIT 500
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Category trends error: {e}")
            return []
        finally:
            conn.close()

        category_stats = {}
        for r in rows:
            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                price = item.get("price", item.get("unit_price", 0)) or 0
                qty = item.get("quantity", item.get("qty", 1)) or 1
                if name not in category_stats:
                    category_stats[name] = {"revenue": 0, "orders": 0}
                category_stats[name]["revenue"] += price * qty
                category_stats[name]["orders"] += 1

        sorted_cats = sorted(
            category_stats.items(),
            key=lambda x: x[1]["revenue"],
            reverse=True,
        )

        return [
            {"category": name, "revenue": round(s["revenue"], 2), "orders": s["orders"]}
            for name, s in sorted_cats
        ]

    @staticmethod
    def get_seasonal_patterns():
        """按月份识别季节性模式"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    CAST(strftime('%m', created_at) AS INTEGER) as month_num,
                    COUNT(*) as orders,
                    COALESCE(SUM(total_amount), 0) as revenue
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                GROUP BY month_num
                ORDER BY month_num
            """).fetchall()
        except Exception:
            return []
        finally:
            conn.close()

        return [dict(r) for r in rows]

    @staticmethod
    def get_demand_by_category(country_code=None):
        """按品类查看需求分布"""
        conn = _read_db()
        try:
            if country_code:
                rows = conn.execute("""
                    SELECT o.items, o.total_amount
                    FROM orders o
                    JOIN customers c ON c.id = o.customer_id
                    WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                      AND c.country = ?
                      AND o.items != '[]' AND o.items IS NOT NULL
                    ORDER BY o.created_at DESC
                    LIMIT 200
                """, (country_code,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT items, total_amount
                    FROM orders
                    WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                      AND items != '[]' AND items IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 500
                """).fetchall()
        except Exception as e:
            logger.warning(f"Demand by category error: {e}")
            return []
        finally:
            conn.close()

        stats = {}
        for r in rows:
            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                price = item.get("price", item.get("unit_price", 0)) or 0
                qty = item.get("quantity", item.get("qty", 1)) or 1
                if name not in stats:
                    stats[name] = 0
                stats[name] += price * qty

        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        return [{"product": name, "revenue": round(rev, 2)} for name, rev in sorted_stats]

    @staticmethod
    def predict_demand(product_category=None, days_forward=30):
        """简单需求预测"""
        conn = _read_db()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as orders,
                    COALESCE(SUM(total_amount), 0) as revenue,
                    COALESCE(AVG(total_amount), 0) as aov
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND created_at >= datetime('now', '-90 days')
            """).fetchone()
        except Exception:
            return {"predicted_orders": 0, "predicted_revenue": 0}
        finally:
            conn.close()

        if row and row["orders"] > 0:
            daily_rate = row["orders"] / 90.0
            daily_revenue = row["revenue"] / 90.0
            return {
                "predicted_orders": round(daily_rate * days_forward),
                "predicted_revenue": round(daily_revenue * days_forward, 2),
                "avg_order_value": round(row["aov"], 2),
                "confidence": "low" if row["orders"] < 30 else "medium",
            }
        return {"predicted_orders": 0, "predicted_revenue": 0, "confidence": "none"}
