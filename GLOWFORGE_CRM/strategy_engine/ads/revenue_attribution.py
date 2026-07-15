"""Revenue Attribution — 收入归因系统

核心问题：「这个订单到底来自哪个广告？」
通过 customers.source / campaign 将订单收入映射回广告来源。
"""
import logging
from datetime import datetime, timedelta

from strategy_engine.db import _read_db

logger = logging.getLogger("revenue_attribution")


class RevenueAttribution:
    """收入归因引擎"""

    @staticmethod
    def attribute_revenue(days=90):
        """执行完整收入归因

        遍历所有订单，通过 customers.source 映射回广告来源。

        返回:
            dict: {
                by_source: { facebook: { revenue, profit, orders, ... } },
                by_campaign: { campaign_name: { ... } },
                summary: { total_revenue, attributed_revenue, ... }
            }
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    o.id AS order_id,
                    o.total_amount,
                    c.source,
                    c.campaign,
                    c.id AS customer_id,
                    c.country
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                  AND (c.source IS NOT NULL AND c.source != '')
                  AND o.created_at >= datetime('now', ? || ' days')
                ORDER BY o.created_at DESC
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Revenue attribution error: {e}")
            return {"by_source": {}, "by_campaign": {}, "summary": {}}
        finally:
            conn.close()

        # 按 source 归因
        by_source = {}
        # 按 campaign 归因
        by_campaign = {}
        # 未归因（有 source 但无 campaign）
        unattributed_revenue = 0

        for r in rows:
            src = r["source"] or "unknown"
            camp = r["campaign"]
            revenue = r["total_amount"] or 0
            country = r["country"] or "unknown"

            # 按 source
            if src not in by_source:
                by_source[src] = {
                    "revenue": 0, "orders": 0,
                    "customers": set(), "countries": set(),
                }
            by_source[src]["revenue"] += revenue
            by_source[src]["orders"] += 1
            by_source[src]["customers"].add(r["customer_id"])
            by_source[src]["countries"].add(country)

            # 按 campaign
            if camp:
                if camp not in by_campaign:
                    by_campaign[camp] = {
                        "source": src, "revenue": 0, "orders": 0,
                        "customers": set(), "countries": set(),
                    }
                by_campaign[camp]["revenue"] += revenue
                by_campaign[camp]["orders"] += 1
                by_campaign[camp]["customers"].add(r["customer_id"])
                by_campaign[camp]["countries"].add(country)
            else:
                unattributed_revenue += revenue

        # 整理输出（转换 set 为 count）
        total_revenue = 0
        for src, data in by_source.items():
            data["revenue"] = round(data["revenue"], 2)
            data["customer_count"] = len(data["customers"])
            data["countries"] = list(data["countries"])
            data["avg_order_value"] = round(
                data["revenue"] / data["orders"], 2
            ) if data["orders"] > 0 else 0
            total_revenue += data["revenue"]
            del data["customers"]

        for camp, data in by_campaign.items():
            data["revenue"] = round(data["revenue"], 2)
            data["customer_count"] = len(data["customers"])
            data["countries"] = list(data["countries"])
            data["avg_order_value"] = round(
                data["revenue"] / data["orders"], 2
            ) if data["orders"] > 0 else 0
            del data["customers"]

        return {
            "by_source": by_source,
            "by_campaign": by_campaign,
            "summary": {
                "total_attributed_revenue": round(total_revenue, 2),
                "unattributed_revenue": round(unattributed_revenue, 2),
                "total_orders": sum(d["orders"] for d in by_source.values()),
                "attributed_sources": len(by_source),
                "attributed_campaigns": len(by_campaign),
                "period_days": days,
            },
        }

    @staticmethod
    def match_order_to_ad_source(order_id):
        """将单个订单映射回广告来源

        返回:
            dict: { order_id, ad_source, campaign, customer_id, revenue }
        """
        conn = _read_db()
        try:
            row = conn.execute("""
                SELECT
                    o.id AS order_id,
                    o.total_amount,
                    c.source,
                    c.campaign,
                    c.id AS customer_id
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.id = ?
            """, (order_id,)).fetchone()
        except Exception as e:
            logger.warning(f"Match order error: {e}")
            return {}
        finally:
            conn.close()

        if not row:
            return {"error": f"Order {order_id} not found"}

        return {
            "order_id": row["order_id"],
            "total_amount": row["total_amount"],
            "ad_source": row["source"] or "unknown",
            "campaign": row["campaign"] or "none",
            "customer_id": row["customer_id"],
            "attributed": row["source"] is not None and row["source"] != "",
        }

    @staticmethod
    def get_attribution_summary():
        """归因覆盖率概览"""
        conn = _read_db()
        try:
            total = conn.execute("""
                SELECT COUNT(*) as cnt,
                       SUM(CASE WHEN c.source IS NOT NULL AND c.source != '' THEN 1 ELSE 0 END) as attributed
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
            """).fetchone()
        except Exception as e:
            logger.warning(f"Attribution summary error: {e}")
            return {}
        finally:
            conn.close()

        if not total:
            return {}

        attr = total["attributed"] or 0
        cnt = total["cnt"] or 1
        return {
            "total_orders_with_customer": cnt,
            "attributed_orders": attr,
            "attribution_rate": round(attr / cnt * 100, 2),
            "gap": cnt - attr,
        }
