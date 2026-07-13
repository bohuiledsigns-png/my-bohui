"""Market Explorer — 市场探索引擎

自动发现赚钱国家。
分析维度：点击率、转化率、客单价、竞争强度。
输出：Top Markets按利润排序 + 新市场推荐。
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class MarketExplorer:
    """市场探索引擎 — 自动发现高利润国家市场"""

    # 国家市场评分（基于模拟数据，实际应用从数据库读取）
    MARKET_SCORES = {
        "AE": {
            "country": "UAE",
            "code": "AE",
            "avg_order_value": 1200,
            "conversion_rate": 8.5,
            "competition_level": "low",
            "market_growth": "high",
            "profit_potential": 95,
            "ease_of_entry": 70,
            "recommendation": "strong_buy",
            "notes": "Luxury market, high willingness to pay premium",
        },
        "US": {
            "country": "United States",
            "code": "US",
            "avg_order_value": 680,
            "conversion_rate": 6.2,
            "competition_level": "high",
            "market_growth": "medium",
            "profit_potential": 80,
            "ease_of_entry": 65,
            "recommendation": "buy",
            "notes": "Large market, competitive but high volume",
        },
        "SA": {
            "country": "Saudi Arabia",
            "code": "SA",
            "avg_order_value": 950,
            "conversion_rate": 7.8,
            "competition_level": "low",
            "market_growth": "very_high",
            "profit_potential": 90,
            "ease_of_entry": 60,
            "recommendation": "strong_buy",
            "notes": "Rapidly growing market, Vision 2030 driving demand",
        },
        "GB": {
            "country": "United Kingdom",
            "code": "GB",
            "avg_order_value": 520,
            "conversion_rate": 5.5,
            "competition_level": "medium",
            "market_growth": "low",
            "profit_potential": 65,
            "ease_of_entry": 75,
            "recommendation": "hold",
            "notes": "Stable market, moderate competition",
        },
        "DE": {
            "country": "Germany",
            "code": "DE",
            "avg_order_value": 580,
            "conversion_rate": 6.0,
            "competition_level": "medium",
            "market_growth": "low",
            "profit_potential": 70,
            "ease_of_entry": 72,
            "recommendation": "buy",
            "notes": "Quality-focused market, technical buyers",
        },
        "AU": {
            "country": "Australia",
            "code": "AU",
            "avg_order_value": 620,
            "conversion_rate": 7.0,
            "competition_level": "low",
            "market_growth": "medium",
            "profit_potential": 75,
            "ease_of_entry": 80,
            "recommendation": "buy",
            "notes": "Growing market, good conversion rates",
        },
        "SG": {
            "country": "Singapore",
            "code": "SG",
            "avg_order_value": 700,
            "conversion_rate": 7.5,
            "competition_level": "medium",
            "market_growth": "medium",
            "profit_potential": 78,
            "ease_of_entry": 85,
            "recommendation": "buy",
            "notes": "Business hub, high purchasing power",
        },
        "QA": {
            "country": "Qatar",
            "code": "QA",
            "avg_order_value": 1100,
            "conversion_rate": 8.0,
            "competition_level": "very_low",
            "market_growth": "high",
            "profit_potential": 92,
            "ease_of_entry": 55,
            "recommendation": "strong_buy",
            "notes": "Wealthy market, luxury construction boom",
        },
        "CA": {
            "country": "Canada",
            "code": "CA",
            "avg_order_value": 580,
            "conversion_rate": 5.8,
            "competition_level": "medium",
            "market_growth": "low",
            "profit_potential": 62,
            "ease_of_entry": 78,
            "recommendation": "hold",
            "notes": "Stable but slow growth",
        },
        "FR": {
            "country": "France",
            "code": "FR",
            "avg_order_value": 550,
            "conversion_rate": 5.2,
            "competition_level": "medium",
            "market_growth": "low",
            "profit_potential": 60,
            "ease_of_entry": 68,
            "recommendation": "hold",
            "notes": "Design-conscious market, moderate potential",
        },
    }

    @staticmethod
    def analyze_markets(min_profit_score: int = 0, limit: int = 10) -> list:
        """分析所有市场并按利润潜力排序

        Args:
            min_profit_score: 最低利润分数过滤
            limit: 返回数量

        Returns:
            list: [{country, code, score, recommendation, ...}]
        """
        markets = []
        for code, data in MarketExplorer.MARKET_SCORES.items():
            # 综合评分 = 利润潜力×0.5 + 转化率×0.25 + 增长×0.25
            growth_score = {"very_low": 20, "low": 40, "medium": 60, "high": 80, "very_high": 95}
            ease_score = {"very_low": 20, "low": 40, "medium": 60, "high": 80}
            competition_penalty = {"very_low": 0, "low": 5, "medium": 15, "high": 25}

            comp_penalty = competition_penalty.get(data["competition_level"], 10)
            growth = growth_score.get(data["market_growth"], 50)

            composite = (
                data["profit_potential"] * 0.5
                + data["conversion_rate"] * 3  # conversion_rate is already a percentage
                + growth * 0.25
                - comp_penalty
            )

            markets.append({
                **data,
                "composite_score": round(composite, 1),
            })

        # 排序
        markets.sort(key=lambda x: x["composite_score"], reverse=True)

        if min_profit_score > 0:
            markets = [m for m in markets if m["profit_potential"] >= min_profit_score]

        return markets[:limit]

    @staticmethod
    def discover_new_markets(product: str = "") -> list:
        """发现值得进入的新市场

        Args:
            product: 产品类型

        Returns:
            list: [{country, reason, potential, risk, action}]
        """
        high_potential = MarketExplorer.analyze_markets(min_profit_score=75, limit=5)

        discoveries = []
        for m in high_potential:
            risk = "low" if m["ease_of_entry"] >= 70 else "medium"
            if m["competition_level"] in ("low", "very_low") and m["market_growth"] in ("high", "very_high"):
                risk = "low"
                action = "enter_now"
            elif m["competition_level"] == "high":
                risk = "medium"
                action = "test_market"
            else:
                risk = "medium"
                action = "further_analysis"

            discoveries.append({
                "country": m["country"],
                "code": m["code"],
                "profit_potential": m["profit_potential"],
                "composite_score": m["composite_score"],
                "risk": risk,
                "recommended_action": action,
                "reason": (
                    f"High profit potential ({m['profit_potential']}/100) with "
                    f"low competition and {m['market_growth']} growth"
                ),
            })

        return discoveries

    @staticmethod
    def get_market_summary() -> dict:
        """获取市场整体摘要"""
        all_markets = MarketExplorer.analyze_markets()
        if not all_markets:
            return {}

        return {
            "total_markets_analyzed": len(MarketExplorer.MARKET_SCORES),
            "top_market": all_markets[0]["country"],
            "top_score": all_markets[0]["composite_score"],
            "bottom_market": all_markets[-1]["country"],
            "average_profit_potential": round(
                sum(m["profit_potential"] for m in all_markets) / len(all_markets), 1
            ),
            "strong_buy_count": sum(1 for m in all_markets if m["recommendation"] == "strong_buy"),
            "buy_count": sum(1 for m in all_markets if m["recommendation"] == "buy"),
            "hold_count": sum(1 for m in all_markets if m["recommendation"] == "hold"),
            "new_market_opportunities": MarketExplorer.discover_new_markets(),
        }


# 快捷入口
explorer = MarketExplorer()


def analyze_markets() -> list:
    return MarketExplorer.analyze_markets()


def discover_new() -> list:
    return MarketExplorer.discover_new_markets()
