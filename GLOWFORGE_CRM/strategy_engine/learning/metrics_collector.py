"""Metrics Collector — 全系统 KPI 收集器

从数据库收集所有关键绩效指标，供策略分析和学习循环使用。
"""
import logging
from datetime import datetime, timedelta

from strategy_engine.db import _read_db, parse_items

logger = logging.getLogger("metrics_collector")


class MetricsCollector:
    """KPI 收集器 — 从 DB 采集所有关键指标"""

    @staticmethod
    def collect_all():
        """收集所有模块的完整 KPI

        返回:
            dict: {
                summary: { total_orders, total_revenue, total_profit,
                           avg_margin, active_customers, conversion_rate },
                product_metrics: {...},
                market_metrics: {...},
                pricing_metrics: {...},
                customer_metrics: {...},
            }
        """
        return {
            "summary": MetricsCollector.collect_summary(),
            "product_metrics": MetricsCollector.collect_product_metrics(),
            "market_metrics": MetricsCollector.collect_market_metrics(),
            "pricing_metrics": MetricsCollector.collect_pricing_metrics(),
            "customer_metrics": MetricsCollector.collect_customer_metrics(),
        }

    @staticmethod
    def collect_summary():
        """收集汇总 KPI"""
        conn = _read_db()
        try:
            # 总订单和营收
            order_row = conn.execute("""
                SELECT COUNT(*) as total_orders,
                       COALESCE(SUM(total_amount), 0) as total_revenue,
                       COALESCE(AVG(CASE WHEN total_amount > 0 THEN total_amount END), 0) as avg_order_value
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed')
            """).fetchone()

            # 活跃客户（30天内有消息）
            cust_row = conn.execute("""
                SELECT COUNT(DISTINCT customer_id) as active
                FROM messages
                WHERE created_at >= datetime('now', '-30 days')
            """).fetchone()

            # 转化率
            conv_row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won
                FROM v3_conversions
                WHERE final_result IN ('won', 'lost')
            """).fetchone()
        except Exception as e:
            logger.warning(f"Summary metrics error: {e}")
            return {}
        finally:
            conn.close()

        conv_rate = (conv_row["won"] / conv_row["total"] * 100
                     if conv_row and conv_row["total"] > 0 else 0)

        return {
            "total_orders": order_row["total_orders"],
            "total_revenue": round(order_row["total_revenue"] or 0, 2),
            "avg_order_value": round(order_row["avg_order_value"] or 0, 2),
            "active_customers_30d": cust_row["active"] if cust_row else 0,
            "conversion_rate": round(conv_rate or 0, 2),
        }

    @staticmethod
    def collect_product_metrics():
        """产品级 KPI"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT o.items, o.total_amount, o.status
                FROM orders o
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND o.items != '[]' AND o.items IS NOT NULL
                ORDER BY o.created_at DESC
                LIMIT 200
            """).fetchall()
        except Exception as e:
            logger.warning(f"Product metrics error: {e}")
            return {}
        finally:
            conn.close()

        # 解析 items JSON（双重编码处理）
        product_stats = {}
        for r in rows:
            items = parse_items(r["items"])
            for item in items:
                name = item.get("name", item.get("product", "unknown"))
                qty = item.get("quantity", item.get("qty", 1)) or 1
                price = item.get("price", item.get("unit_price", 0)) or 0
                if name not in product_stats:
                    product_stats[name] = {"revenue": 0, "orders": 0, "units": 0}
                product_stats[name]["revenue"] += price * qty
                product_stats[name]["orders"] += 1
                product_stats[name]["units"] += qty

        top = sorted(product_stats.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]
        return {
            "product_count": len(product_stats),
            "top_by_revenue": [
                {"name": n, "revenue": round(s["revenue"], 2), "orders": s["orders"]}
                for n, s in top
            ],
        }

    @staticmethod
    def collect_market_metrics():
        """市场级 KPI"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT c.country,
                       COUNT(DISTINCT c.id) as customers,
                       COUNT(DISTINCT o.id) as orders,
                       COALESCE(SUM(o.total_amount), 0) as revenue
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed')
                WHERE c.country != '' AND c.country IS NOT NULL
                GROUP BY c.country
                ORDER BY revenue DESC
                LIMIT 10
            """).fetchall()
        except Exception as e:
            logger.warning(f"Market metrics error: {e}")
            return {}
        finally:
            conn.close()

        return {
            "top_by_revenue": [dict(r) for r in rows],
            "market_count": len(rows),
        }

    @staticmethod
    def collect_pricing_metrics():
        """定价级 KPI"""
        conn = _read_db()
        try:
            margin_row = conn.execute("""
                SELECT COALESCE(AVG(o.total_amount - COALESCE(pc.base_cost, 0)), 0) as avg_margin
                FROM orders o
                LEFT JOIN production_costs pc ON pc.product_category = 'general'
                WHERE o.status IN ('shipped', 'delivered', 'completed')
            """).fetchone()

            price_row = conn.execute("""
                SELECT MIN(total_amount) as min_price,
                       MAX(total_amount) as max_price,
                       AVG(total_amount) as avg_price
                FROM orders
                WHERE status IN ('shipped', 'delivered', 'completed')
                  AND total_amount > 0
            """).fetchone()
        except Exception as e:
            logger.warning(f"Pricing metrics error: {e}")
            return {}
        finally:
            conn.close()

        return {
            "avg_margin": round(margin_row["avg_margin"] or 0, 2),
            "price_range": {
                "min": price_row["min_price"] if price_row else 0,
                "max": price_row["max_price"] if price_row else 0,
                "avg": round(price_row["avg_price"] or 0, 2) if price_row else 0,
            },
        }

    @staticmethod
    def collect_customer_metrics():
        """客户级 KPI"""
        conn = _read_db()
        try:
            # 按 lead_state 分布
            state_rows = conn.execute("""
                SELECT lead_state, COUNT(*) as cnt
                FROM customers
                WHERE lead_state IS NOT NULL AND lead_state != ''
                GROUP BY lead_state
                ORDER BY cnt DESC
            """).fetchall()

            # 按国家分布
            country_rows = conn.execute("""
                SELECT country, COUNT(*) as cnt
                FROM customers
                WHERE country != '' AND country IS NOT NULL
                GROUP BY country
                ORDER BY cnt DESC
                LIMIT 10
            """).fetchall()

            # 总数
            total = conn.execute("SELECT COUNT(*) as cnt FROM customers").fetchone()
            new_30d = conn.execute("""
                SELECT COUNT(*) as cnt FROM customers
                WHERE created_at >= datetime('now', '-30 days')
            """).fetchone()
        except Exception as e:
            logger.warning(f"Customer metrics error: {e}")
            return {}
        finally:
            conn.close()

        return {
            "total": total["cnt"] if total else 0,
            "new_30d": new_30d["cnt"] if new_30d else 0,
            "by_lead_state": {r["lead_state"]: r["cnt"] for r in state_rows},
            "by_country": {r["country"]: r["cnt"] for r in country_rows},
        }
