"""Conversion Tracker — 转化追踪

把广告流量连接到 CRM 成交路径：
Ad Click → WhatsApp → Conversation → Quote → Order
"""
import logging
from datetime import datetime, timedelta

from strategy_engine.db import _read_db

logger = logging.getLogger("conversion_tracker")

CONVERSION_STAGES = ["lead", "contacted", "quoted", "ordered"]


class ConversionTracker:
    """转化追踪引擎"""

    @staticmethod
    def track_conversions(days=30):
        """追踪各广告来源的转化漏斗

        返回:
            dict: {
                by_source: {
                    facebook: {
                        leads, contacted, quoted, ordered,
                        funnel: [stage, stage, ...],
                        conversion_paths: [{...}]
                    }
                }
            }
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    c.id, c.source, c.campaign, c.lead_state,
                    c.first_contacted_at, c.created_at,
                    COUNT(DISTINCT q.id) AS quote_count,
                    COUNT(DISTINCT o.id) AS order_count,
                    COALESCE(SUM(o.total_amount), 0) AS order_revenue
                FROM customers c
                LEFT JOIN quotes q ON q.customer_id = c.id
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                WHERE c.source IS NOT NULL AND c.source != ''
                  AND c.created_at >= datetime('now', ? || ' days')
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Conversion tracking error: {e}")
            return {}
        finally:
            conn.close()

        # 按来源聚合漏斗
        funnel = {}
        for r in rows:
            src = r["source"] or "unknown"
            if src not in funnel:
                funnel[src] = {
                    "leads": 0, "contacted": 0,
                    "quoted": 0, "ordered": 0,
                    "revenue": 0, "avg_order_value": 0,
                }

            funnel[src]["leads"] += 1
            if r["first_contacted_at"]:
                funnel[src]["contacted"] += 1
            if r["quote_count"] and r["quote_count"] > 0:
                funnel[src]["quoted"] += 1
            if r["order_count"] and r["order_count"] > 0:
                funnel[src]["ordered"] += 1
                funnel[src]["revenue"] += r["order_revenue"] or 0

        # 计算转化率和漏斗效率
        for src, data in funnel.items():
            data["revenue"] = round(data["revenue"], 2)
            data["avg_order_value"] = round(
                data["revenue"] / data["ordered"], 2
            ) if data["ordered"] > 0 else 0
            data["lead_to_contacted"] = round(
                data["contacted"] / data["leads"] * 100, 2
            ) if data["leads"] > 0 else 0
            data["contacted_to_quoted"] = round(
                data["quoted"] / data["contacted"] * 100, 2
            ) if data["contacted"] > 0 else 0
            data["quoted_to_ordered"] = round(
                data["ordered"] / data["quoted"] * 100, 2
            ) if data["quoted"] > 0 else 0
            data["overall_conversion"] = round(
                data["ordered"] / data["leads"] * 100, 2
            ) if data["leads"] > 0 else 0

        return {
            "by_source": funnel,
            "total_sources": len(funnel),
            "total_leads": sum(d["leads"] for d in funnel.values()),
            "total_orders": sum(d["ordered"] for d in funnel.values()),
            "period_days": days,
        }

    @staticmethod
    def track_funnel_by_campaign(days=30):
        """按广告活动追踪转化漏斗"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    c.campaign, c.source,
                    COUNT(DISTINCT c.id) AS leads,
                    SUM(CASE WHEN c.first_contacted_at IS NOT NULL THEN 1 ELSE 0 END) AS contacted,
                    COUNT(DISTINCT q.id) AS quotes,
                    COUNT(DISTINCT o.id) AS orders,
                    COALESCE(SUM(o.total_amount), 0) AS revenue
                FROM customers c
                LEFT JOIN quotes q ON q.customer_id = c.id
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                WHERE c.campaign IS NOT NULL AND c.campaign != ''
                  AND c.created_at >= datetime('now', ? || ' days')
                GROUP BY c.campaign
                ORDER BY revenue DESC
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Campaign funnel error: {e}")
            return {}
        finally:
            conn.close()

        result = {}
        for r in rows:
            camp = r["campaign"]
            result[camp] = {
                "source": r["source"],
                "leads": r["leads"],
                "contacted": r["contacted"],
                "quotes": r["quotes"],
                "orders": r["orders"],
                "revenue": round(r["revenue"] or 0, 2),
                "conv_rate": round(r["orders"] / r["leads"] * 100, 2) if r["leads"] > 0 else 0,
            }

        return result

    @staticmethod
    def get_source_timeline(source, days=30):
        """获取特定广告来源的每日表现时间线"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    DATE(c.created_at) AS day,
                    COUNT(*) AS new_leads
                FROM customers c
                WHERE c.source = ?
                  AND c.created_at >= datetime('now', ? || ' days')
                GROUP BY DATE(c.created_at)
                ORDER BY day
            """, (source, f"-{days}")).fetchall()
        except Exception as e:
            logger.warning(f"Source timeline error: {e}")
            return []
        finally:
            conn.close()

        return [dict(r) for r in rows]
