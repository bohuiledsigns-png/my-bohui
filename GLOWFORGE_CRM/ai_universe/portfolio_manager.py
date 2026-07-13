"""Portfolio Manager — 多公司管理系统

系统自动管理多个公司：
  - 哪个公司赚钱
  - 哪个市场增长
  - 哪个产品失败
"""

import sys
import os
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class PortfolioManager:
    """投资组合管理器 — 多公司健康监控"""

    def __init__(self):
        self.companies = []

    def register_company(self, company_data: dict) -> dict:
        """注册一个公司到投资组合

        Args:
            company_data: {name, market, industry, focus, invested, ...}

        Returns:
            dict: 注册确认 + 公司ID
        """
        company_id = f"co_{len(self.companies) + 1}_{int(datetime.now().timestamp())}"

        entry = {
            "id": company_id,
            "name": company_data.get("name", "Unnamed"),
            "market": company_data.get("market", ""),
            "industry": company_data.get("industry", ""),
            "focus": company_data.get("focus", ""),
            "invested": company_data.get("invested", 0),
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "metrics": {
                "revenue": 0,
                "profit": 0,
                "customers": 0,
                "growth_pct": 0,
            },
        }

        self.companies.append(entry)
        return entry

    def update_metrics(self, company_id: str, metrics: dict) -> bool:
        """更新公司指标"""
        for company in self.companies:
            if company["id"] == company_id:
                company["metrics"].update(metrics)
                company["updated_at"] = datetime.now().isoformat()
                return True
        return False

    def get_portfolio_summary(self) -> dict:
        """获取投资组合摘要"""
        if not self.companies:
            return {"total_companies": 0, "total_invested": 0, "total_revenue": 0}

        total_invested = sum(c.get("invested", 0) for c in self.companies)
        total_revenue = sum(c["metrics"].get("revenue", 0) for c in self.companies)
        total_profit = sum(c["metrics"].get("profit", 0) for c in self.companies)
        total_customers = sum(c["metrics"].get("customers", 0) for c in self.companies)

        # 按表现排序
        sorted_companies = sorted(
            self.companies,
            key=lambda c: c["metrics"].get("profit", 0),
            reverse=True,
        )

        return {
            "total_companies": len(self.companies),
            "total_invested": total_invested,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_customers": total_customers,
            "overall_roi": round(
                (total_profit / total_invested * 100) if total_invested > 0 else 0, 1
            ),
            "best_performer": sorted_companies[0]["name"] if sorted_companies else "",
            "worst_performer": sorted_companies[-1]["name"] if len(sorted_companies) > 1 else "",
            "companies": sorted_companies,
        }

    def analyze_portfolio(self) -> dict:
        """分析投资组合健康度"""
        summary = self.get_portfolio_summary()
        if summary["total_companies"] == 0:
            return {"health": "empty", "recommendations": ["Register companies first"]}

        warnings = []
        opportunities = []

        # 检查集中度风险
        if summary["total_companies"] == 1:
            warnings.append("Single company — extreme concentration risk")

        # 检查盈利性
        if summary["total_profit"] < 0:
            warnings.append("Overall portfolio is unprofitable")
        elif summary["total_profit"] == 0:
            warnings.append("No profit data yet")

        # 检查增长
        losing_companies = [
            c for c in summary.get("companies", [])
            if c["metrics"].get("profit", 0) < 0
        ]
        if losing_companies:
            warnings.append(
                f"{len(losing_companies)} company(ies) losing money: "
                f"{', '.join(c['name'] for c in losing_companies[:3])}"
            )

        # 机会
        growing = [
            c for c in summary.get("companies", [])
            if c["metrics"].get("growth_pct", 0) > 20
        ]
        if growing:
            opportunities.append(
                f"Consider increasing investment in growing companies: "
                f"{', '.join(c['name'] for c in growing[:2])}"
            )

        return {
            "health": "good" if len(warnings) == 0 else "needs_attention",
            "summary": summary,
            "warnings": warnings,
            "opportunities": opportunities,
            "recommendations": [
                "Diversify into new markets" if "concentration" in str(warnings) else "",
                "Cut underperforming companies" if losing_companies else "",
                "Double down on winners" if opportunities else "",
            ],
        }

    def get_growth_recommendations(self) -> list:
        """获取增长建议"""
        summary = self.get_portfolio_summary()
        recommendations = []

        if summary["total_companies"] == 0:
            return ["Start by registering companies"]

        companies = summary.get("companies", [])

        # 优胜者扩张
        if companies:
            best = companies[0]
            if best["metrics"].get("profit", 0) > 0:
                recommendations.append(
                    f"Expand {best['name']} — increase marketing budget by 30%"
                )

        # 新市场机会
        markets_covered = set(c.get("market", "") for c in self.companies)
        target_markets = {"AE", "US", "GB", "AU", "SA", "SG"}
        missing = target_markets - markets_covered
        if missing:
            recommendations.append(
                f"Explore untapped markets: {', '.join(sorted(missing)[:3])}"
            )

        # 多样化建议
        industries = set(c.get("industry", "") for c in self.companies)
        if len(industries) <= 1:
            recommendations.append(
                "Consider adjacent industries (e.g., lighting, furniture)"
            )

        return recommendations


# 快捷入口
portfolio = PortfolioManager()


def register(name: str, market: str, industry: str, invested: float = 0) -> dict:
    return portfolio.register_company({
        "name": name, "market": market,
        "industry": industry, "invested": invested,
    })


def analyze() -> dict:
    return portfolio.analyze_portfolio()
