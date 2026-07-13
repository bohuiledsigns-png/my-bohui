"""ROI Engine — 核心利润引擎

不是看「花了多少钱」，而是「每个广告赚了多少钱」。
ROI = (Revenue - Ad Cost) / Ad Cost
"""
import logging
from datetime import datetime, timedelta

from strategy_engine.db import _read_db

logger = logging.getLogger("roi_engine")

# 各渠道默认成本估算（用户可覆盖）
DEFAULT_COST_PER_LEAD = {
    "facebook": 8.0,
    "google": 10.0,
    "tiktok": 6.0,
    "manual": 0,
}


class ROIEngine:
    """ROI 计算引擎"""

    @staticmethod
    def calculate_roi(attribution_data=None, cost_per_lead=None):
        """计算每个广告来源/活动的 ROI

        参数:
            attribution_data: RevenueAttribution.attribute_revenue() 的输出
            cost_per_lead: 可选，覆盖各渠道单条线索成本

        返回:
            dict: {
                by_source: { source: { roi, profit, revenue, cost, ... } },
                by_campaign: { campaign: { ... } },
                summary: { overall_roi, total_profit, ... }
            }
        """
        if attribution_data is None:
            from strategy_engine.ads.revenue_attribution import RevenueAttribution
            attribution_data = RevenueAttribution.attribute_revenue()

        costs = cost_per_lead or DEFAULT_COST_PER_LEAD

        # 按来源计算 ROI
        by_source = {}
        for src, data in attribution_data.get("by_source", {}).items():
            revenue = data.get("revenue", 0)
            orders = data.get("orders", 0)
            customers = data.get("customer_count", 0)
            lead_cost = costs.get(src, 8.0)

            estimated_ad_cost = customers * lead_cost
            profit = revenue - estimated_ad_cost
            roi = profit / estimated_ad_cost if estimated_ad_cost > 0 else 0

            by_source[src] = {
                "revenue": round(revenue, 2),
                "orders": orders,
                "estimated_ad_cost": round(estimated_ad_cost, 2),
                "profit": round(profit, 2),
                "roi": round(roi, 2),
                "cost_per_lead": lead_cost,
                "customers": customers,
                "verdict": ROIEngine._verdict(roi),
            }

        # 按活动计算 ROI
        by_campaign = {}
        for camp, data in attribution_data.get("by_campaign", {}).items():
            revenue = data.get("revenue", 0)
            orders = data.get("orders", 0)
            src = data.get("source", "unknown")
            lead_cost = costs.get(src, 8.0)
            customers = data.get("customer_count", 0)

            estimated_ad_cost = customers * lead_cost
            profit = revenue - estimated_ad_cost
            roi = profit / estimated_ad_cost if estimated_ad_cost > 0 else 0

            by_campaign[camp] = {
                "source": src,
                "revenue": round(revenue, 2),
                "orders": orders,
                "estimated_ad_cost": round(estimated_ad_cost, 2),
                "profit": round(profit, 2),
                "roi": round(roi, 2),
                "customers": customers,
                "verdict": ROIEngine._verdict(roi),
            }

        # 汇总
        total_revenue = sum(d["revenue"] for d in by_source.values())
        total_cost = sum(d["estimated_ad_cost"] for d in by_source.values())
        total_profit = total_revenue - total_cost

        summary = {
            "total_revenue": round(total_revenue, 2),
            "total_ad_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "overall_roi": round(total_profit / total_cost, 2) if total_cost > 0 else 0,
            "sources_analyzed": len(by_source),
            "campaigns_analyzed": len(by_campaign),
        }

        return {
            "by_source": by_source,
            "by_campaign": by_campaign,
            "summary": summary,
        }

    @staticmethod
    def _verdict(roi):
        """基于 ROI 给出判定"""
        if roi >= 3:
            return "excellent"
        elif roi >= 2:
            return "good"
        elif roi >= 1:
            return "marginal"
        elif roi >= 0:
            return "breakeven"
        return "loss"

    @staticmethod
    def get_roi_report(days=90):
        """生成完整 ROI 报告（一步到位）"""
        from strategy_engine.ads.revenue_attribution import RevenueAttribution
        from strategy_engine.ads.ad_tracker import AdTracker

        attribution = RevenueAttribution.attribute_revenue(days=days)
        ad_metrics = AdTracker.collect_ad_metrics(days=days)
        roi = ROIEngine.calculate_roi(attribution_data=attribution)

        return {
            "report_date": datetime.now().isoformat(),
            "period_days": days,
            "roi": roi,
            "ad_metrics": ad_metrics,
            "attribution": attribution,
        }

    @staticmethod
    def source_comparison():
        """横向对比各广告渠道效率"""
        attribution = RevenueAttribution.attribute_revenue()
        roi_data = ROIEngine.calculate_roi(attribution_data=attribution)

        rows = []
        for src, data in roi_data.get("by_source", {}).items():
            rows.append({
                "source": src,
                "roi": data["roi"],
                "profit": data["profit"],
                "revenue": data["revenue"],
                "cost": data["estimated_ad_cost"],
                "orders": data["orders"],
                "verdict": data["verdict"],
            })

        rows.sort(key=lambda x: x["roi"], reverse=True)
        return rows
