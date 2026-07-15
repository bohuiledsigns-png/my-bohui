"""Market Spinup — 新市场启动器

新市场自动启动流程：
  1. AI生成内容
  2. 自动投广告
  3. 自动建落地页
  4. 自动引流WhatsApp
  5. 接入V6销售系统

本质：新市场 = 一键启动
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class MarketSpinup:
    """新市场启动器 — 一键启动新市场"""

    # 启动阶段定义
    SPINUP_PHASES = [
        {
            "phase": 1,
            "name": "Market Research",
            "days": 2,
            "tasks": ["analyze_competition", "identify_keywords", "study_culture"],
            "auto": True,
        },
        {
            "phase": 2,
            "name": "Content Creation",
            "days": 3,
            "tasks": ["generate_ads", "create_landing_page", "prepare_catalog"],
            "auto": True,
        },
        {
            "phase": 3,
            "name": "Channel Setup",
            "days": 2,
            "tasks": ["setup_whatsapp", "create_ad_accounts", "configure_tracking"],
            "auto": True,
        },
        {
            "phase": 4,
            "name": "Test Launch",
            "days": 7,
            "tasks": ["run_test_ads", "monitor_ctr", "collect_data"],
            "auto": True,
        },
        {
            "phase": 5,
            "name": "Optimization",
            "days": 5,
            "tasks": ["optimize_ads", "refine_targeting", "adjust_pricing"],
            "auto": True,
        },
        {
            "phase": 6,
            "name": "Scale",
            "days": 10,
            "tasks": ["scale_budget", "expand_channels", "build_presence"],
            "auto": True,
        },
    ]

    @staticmethod
    def create_launch_plan(product: str, target_market: str,
                           industry: str = "", budget: float = 2000) -> dict:
        """创建新市场启动计划

        Args:
            product: 产品
            target_market: 目标市场代码
            industry: 行业
            budget: 初始预算

        Returns:
            dict: 完整启动计划
        """
        phases = []
        total_days = 0

        for phase_config in MarketSpinup.SPINUP_PHASES:
            start_day = total_days + 1
            end_day = total_days + phase_config["days"]
            total_days += phase_config["days"]

            phases.append({
                "phase": phase_config["phase"],
                "name": phase_config["name"],
                "days": phase_config["days"],
                "start_day": start_day,
                "end_day": end_day,
                "tasks": phase_config["tasks"],
                "auto": phase_config["auto"],
                "deliverables": MarketSpinup._get_phase_deliverables(
                    phase_config["name"], product, target_market
                ),
            })

        # 生成品牌和落地页
        brand = MarketSpinup._generate_quick_brand(product, target_market, industry)

        # 预算分配
        budget_breakdown = MarketSpinup._allocate_budget(budget, phases)

        return {
            "product": product,
            "target_market": target_market,
            "industry": industry or "signage",
            "total_days": total_days,
            "estimated_launch_date": (datetime.now() + timedelta(days=total_days)).strftime("%Y-%m-%d"),
            "total_budget": budget,
            "brand_suggestion": brand,
            "phases": phases,
            "budget_breakdown": budget_breakdown,
            "critical_success_factors": [
                "WhatsApp response within 5 minutes",
                "First ad results within 48 hours",
                "Continuous A/B testing from day 8",
            ],
            "automation_level": "90% automated — manual review only for brand approval",
        }

    @staticmethod
    def _get_phase_deliverables(phase_name: str, product: str, market: str) -> list:
        """获取各阶段交付物"""
        deliverables = {
            "Market Research": [
                f"Competitor analysis for {product} in {market}",
                "Keyword list (50+ terms)",
                "Cultural adaptation guide",
            ],
            "Content Creation": [
                f"10 ad creatives for {product}",
                f"Landing page optimized for {market}",
                f"Product catalog in local language",
            ],
            "Channel Setup": [
                f"WhatsApp Business account for {market}",
                "Ad accounts created (Meta/Google/TikTok)",
                "Conversion tracking configured",
            ],
            "Test Launch": [
                f"5 ad sets running at ${50}/day",
                "CTR and conversion monitoring",
                "A/B test results",
            ],
            "Optimization": [
                "Winning ad sets identified",
                "Budget shifted to best performers",
                "Pricing optimized for market",
            ],
            "Scale": [
                f"Daily budget scaled to ${200}/day",
                "2+ channels active",
                "First 10+ leads generated",
            ],
        }
        return deliverables.get(phase_name, [])

    @staticmethod
    def _generate_quick_brand(product: str, market: str, industry: str) -> dict:
        """快速生成品牌建议"""
        market_names = {"AE": "Dubai", "US": "America", "GB": "London", "AU": "Sydney"}
        hint = market_names.get(market, market)

        return {
            "suggested_name": f"GlowForge {hint}",
            "tagline": f"Premium {product.replace('_', ' ')} for {hint}",
            "domain": f"glowforge-{market.lower()}.com",
        }

    @staticmethod
    def _allocate_budget(total: float, phases: list) -> list:
        """分配预算到各阶段"""
        phase_weights = {1: 0.05, 2: 0.15, 3: 0.10, 4: 0.35, 5: 0.20, 6: 0.15}

        breakdown = []
        for p in phases:
            weight = phase_weights.get(p["phase"], 0.1)
            amount = round(total * weight, 2)
            breakdown.append({
                "phase": p["phase"],
                "name": p["name"],
                "budget": amount,
                "pct": round(weight * 100, 1),
            })

        return breakdown

    @staticmethod
    def estimate_success_probability(product: str, market: str) -> dict:
        """估算新市场成功率

        Args:
            product: 产品
            market: 市场代码

        Returns:
            dict: {probability, factors, recommendations}
        """
        from ai_engine.market_explorer import MarketExplorer
        markets = MarketExplorer.analyze_markets()
        market_data = next((m for m in markets if m["code"] == market), None)

        if not market_data:
            return {
                "probability": "unknown",
                "factors": ["Market data not available"],
                "recommendations": ["Run market research first"],
            }

        score = market_data.get("composite_score", 50)
        competition = market_data.get("competition_level", "medium")

        if score >= 80 and competition in ("low", "very_low"):
            prob = "high"
        elif score >= 60:
            prob = "medium"
        else:
            prob = "low"

        return {
            "probability": prob,
            "composite_score": score,
            "factors": [
                f"Profit potential: {market_data.get('profit_potential', 50)}/100",
                f"Competition: {competition}",
                f"Market growth: {market_data.get('market_growth', 'medium')}",
            ],
            "recommendations": [
                "Start with small test budget" if prob != "high" else "Full launch recommended",
                "Monitor first 7 days closely",
                "Prepare quick pivot if CTR below 2%",
            ],
        }


# 快捷入口
spinup = MarketSpinup()


def create_plan(product: str, market: str, budget: float = 2000) -> dict:
    return MarketSpinup.create_launch_plan(product, market, budget=budget)


def estimate_success(product: str, market: str) -> dict:
    return MarketSpinup.estimate_success_probability(product, market)
