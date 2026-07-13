"""Margin Analyzer — 利润结构分析

分析各产品的利润率结构、成本构成、利润趋势。
"""
import logging

from strategy_engine.db import _read_db, parse_items

logger = logging.getLogger("margin_analyzer")


class MarginAnalyzer:
    """利润结构分析引擎"""

    @staticmethod
    def analyze_product_margins():
        """分析各产品利润率"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT o.items, o.total_amount
                FROM orders o
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND o.items != '[]' AND o.items IS NOT NULL
                ORDER BY o.created_at DESC
                LIMIT 300
            """).fetchall()

            cost_row = conn.execute("""
                SELECT COALESCE(AVG(base_cost), 0) as avg_cost
                FROM production_costs
            """).fetchone()
        except Exception as e:
            logger.warning(f"Product margin analysis error: {e}")
            return []
        finally:
            conn.close()

        base_cost = cost_row["avg_cost"] if cost_row else 0

        product_margins = {}
        for r in rows:
            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                price = item.get("price", item.get("unit_price", 0)) or 0
                qty = item.get("quantity", item.get("qty", 1)) or 1

                if name not in product_margins:
                    product_margins[name] = {"revenue": 0, "cost": 0, "orders": 0}

                item_revenue = price * qty
                item_cost = base_cost * qty
                product_margins[name]["revenue"] += item_revenue
                product_margins[name]["cost"] += item_cost
                product_margins[name]["orders"] += 1

        results = []
        for name, stats in product_margins.items():
            margin_pct = 0
            if stats["revenue"] > 0:
                margin_pct = round(
                    (stats["revenue"] - stats["cost"]) / stats["revenue"] * 100, 2
                )

            results.append({
                "product": name,
                "revenue": round(stats["revenue"], 2),
                "estimated_cost": round(stats["cost"], 2),
                "margin_pct": margin_pct,
                "orders": stats["orders"],
            })

        results.sort(key=lambda x: x["margin_pct"], reverse=True)
        for i, r in enumerate(results):
            r["margin_rank"] = i + 1

        return results

    @staticmethod
    def analyze_cost_structure():
        """成本结构概览"""
        conn = _read_db()
        try:
            total_revenue = conn.execute("""
                SELECT COALESCE(SUM(total_amount), 0) as revenue
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
            """).fetchone()

            avg_cost = conn.execute("""
                SELECT COALESCE(AVG(base_cost), 0) as avg_cost
                FROM production_costs
            """).fetchone()

            order_count = conn.execute("""
                SELECT COUNT(*) as cnt
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
            """).fetchone()
        except Exception as e:
            logger.warning(f"Cost structure error: {e}")
            return {}
        finally:
            conn.close()

        rev = total_revenue["revenue"] if total_revenue else 0
        cnt = order_count["cnt"] if order_count else 0
        avg_unit_cost = avg_cost["avg_cost"] if avg_cost else 0

        estimated_total_cost = avg_unit_cost * cnt
        estimated_margin = rev - estimated_total_cost
        margin_pct = round(estimated_margin / rev * 100, 2) if rev > 0 else 0

        return {
            "total_revenue": round(rev, 2),
            "estimated_total_cost": round(estimated_total_cost, 2),
            "estimated_gross_margin": round(estimated_margin, 2),
            "margin_pct": margin_pct,
            "avg_unit_cost": round(avg_unit_cost, 2),
            "total_orders": cnt,
        }

    @staticmethod
    def get_margin_trend():
        """利润率月度趋势"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    strftime('%Y-%m', created_at) as month,
                    COUNT(*) as orders,
                    COALESCE(SUM(total_amount), 0) as revenue
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND created_at >= datetime('now', '-180 days')
                GROUP BY strftime('%Y-%m', created_at)
                ORDER BY month
            """).fetchall()
        except Exception as e:
            logger.warning(f"Margin trend error: {e}")
            return []
        finally:
            conn.close()

        monthly = [dict(r) for r in rows]

        conn = _read_db()
        try:
            avg_cost = conn.execute("""
                SELECT COALESCE(AVG(base_cost), 0) as avg_cost
                FROM production_costs
            """).fetchone()
        except Exception:
            avg_cost = {"avg_cost": 0}
        finally:
            conn.close()

        base = avg_cost["avg_cost"] if avg_cost else 0

        for m in monthly:
            est_cost = base * m["orders"]
            m["estimated_cost"] = round(est_cost, 2)
            m["estimated_margin_pct"] = round(
                (m["revenue"] - est_cost) / m["revenue"] * 100, 2
            ) if m["revenue"] > 0 else 0

        return monthly
