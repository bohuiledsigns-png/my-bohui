"""Ad Tracker — 广告数据采集层

从 CRM 已有数据（customers.source/campaign + campaigns 表）
聚合广告表现指标。实际广告平台 API 接入时可扩展各平台 tracker。
"""
import logging
from datetime import datetime, timedelta

from strategy_engine.db import _read_db

logger = logging.getLogger("ad_tracker")

ESTIMATED_CPC = 0.50       # 默认 CPC 估算
ESTIMATED_LEAD_COST = 8.0  # 默认单条线索成本


class AdTracker:
    """广告数据采集引擎"""

    @staticmethod
    def collect_ad_metrics(days=30):
        """从 DB 聚合广告表现指标

        返回:
            dict: {
                summary: { total_impressions, total_cost, total_clicks, ... },
                by_source: { facebook: {...}, google: {...}, ... },
                by_campaign: { campaign_name: {...} }
            }
        """
        # 按 source 聚合客户和订单
        source_data = AdTracker._aggregate_by_source(days)
        # 按 campaign 聚合
        campaign_data = AdTracker._aggregate_by_campaign(days)
        # 汇总
        summary = AdTracker._calc_summary(source_data)

        return {
            "summary": summary,
            "by_source": source_data,
            "by_campaign": campaign_data,
            "period_days": days,
        }

    @staticmethod
    def _aggregate_by_source(days):
        """按广告来源聚合"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    c.source,
                    COUNT(DISTINCT c.id) AS leads,
                    COUNT(DISTINCT o.id) AS orders,
                    COALESCE(SUM(o.total_amount), 0) AS revenue
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                WHERE c.source IS NOT NULL AND c.source != ''
                  AND c.created_at >= datetime('now', ? || ' days')
                GROUP BY c.source
                ORDER BY revenue DESC
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Aggregate by source error: {e}")
            return {}
        finally:
            conn.close()

        result = {}
        for r in rows:
            src = r["source"]
            leads = r["leads"]
            orders = r["orders"]
            revenue = r["revenue"] or 0
            est_cost = leads * ESTIMATED_LEAD_COST
            profit = revenue - est_cost

            result[src] = {
                "leads": leads,
                "orders": orders,
                "revenue": round(revenue, 2),
                "estimated_cost": round(est_cost, 2),
                "estimated_profit": round(profit, 2),
                "conversion_rate": round(orders / leads * 100, 2) if leads > 0 else 0,
                "roi": round(profit / est_cost, 2) if est_cost > 0 else 0,
            }

        return result

    @staticmethod
    def _aggregate_by_campaign(days):
        """按广告活动聚合"""
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT
                    c.campaign,
                    c.source,
                    COUNT(DISTINCT c.id) AS leads,
                    COUNT(DISTINCT o.id) AS orders,
                    COALESCE(SUM(o.total_amount), 0) AS revenue
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                WHERE c.campaign IS NOT NULL AND c.campaign != ''
                  AND c.created_at >= datetime('now', ? || ' days')
                GROUP BY c.campaign
                ORDER BY revenue DESC
            """, (f"-{days}",)).fetchall()
        except Exception as e:
            logger.warning(f"Aggregate by campaign error: {e}")
            return {}
        finally:
            conn.close()

        result = {}
        for r in rows:
            camp = r["campaign"]
            leads = r["leads"]
            orders = r["orders"]
            revenue = r["revenue"] or 0
            est_cost = leads * ESTIMATED_LEAD_COST
            profit = revenue - est_cost

            result[camp] = {
                "source": r["source"],
                "leads": leads,
                "orders": orders,
                "revenue": round(revenue, 2),
                "estimated_cost": round(est_cost, 2),
                "estimated_profit": round(profit, 2),
                "conversion_rate": round(orders / leads * 100, 2) if leads > 0 else 0,
                "roi": round(profit / est_cost, 2) if est_cost > 0 else 0,
            }

        return result

    @staticmethod
    def _calc_summary(source_data):
        """计算汇总指标"""
        total_leads = sum(s.get("leads", 0) for s in source_data.values())
        total_orders = sum(s.get("orders", 0) for s in source_data.values())
        total_revenue = sum(s.get("revenue", 0) for s in source_data.values())
        total_cost = sum(s.get("estimated_cost", 0) for s in source_data.values())
        total_profit = total_revenue - total_cost

        return {
            "total_leads": total_leads,
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "total_estimated_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "overall_roi": round(total_profit / total_cost, 2) if total_cost > 0 else 0,
            "overall_conversion_rate": round(total_orders / total_leads * 100, 2) if total_leads > 0 else 0,
            "active_sources": len(source_data),
        }

    @staticmethod
    def get_campaign_performance(campaign_name):
        """获取单个广告活动详情"""
        conn = _read_db()
        try:
            row = conn.execute("""
                SELECT
                    c.campaign, c.source,
                    COUNT(DISTINCT c.id) AS leads,
                    COUNT(DISTINCT o.id) AS orders,
                    COALESCE(SUM(o.total_amount), 0) AS revenue,
                    COUNT(DISTINCT m.id) AS messages
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed', 'pending_approval', 'in_production')
                LEFT JOIN messages m ON m.customer_id = c.id
                WHERE c.campaign = ?
                GROUP BY c.campaign
            """, (campaign_name,)).fetchone()
        except Exception as e:
            logger.warning(f"Campaign performance error: {e}")
            return {}
        finally:
            conn.close()

        if not row:
            return {"error": f"Campaign '{campaign_name}' not found"}

        r = dict(row)
        leads = r["leads"]
        orders = r["orders"]
        revenue = r["revenue"] or 0
        est_cost = leads * ESTIMATED_LEAD_COST

        return {
            "campaign": r["campaign"],
            "source": r["source"],
            "leads": leads,
            "orders": orders,
            "messages": r["messages"],
            "revenue": round(revenue, 2),
            "estimated_cost": round(est_cost, 2),
            "estimated_profit": round(revenue - est_cost, 2),
            "conversion_rate": round(orders / leads * 100, 2) if leads > 0 else 0,
            "roi": round((revenue - est_cost) / est_cost, 2) if est_cost > 0 else 0,
        }
