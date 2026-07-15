"""Channel Distributor — 多渠道分发系统

AI自动将内容分发到多个平台，并自动试错优化。
平台：TikTok Ads / Meta Ads / Google Ads / Pinterest / SEO Blog / WhatsApp Broadcast
"""

import sys
import os
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class ChannelDistributor:
    """多渠道分发系统 — AI自动试错投放"""

    # 平台配置
    PLATFORMS = {
        "tiktok_ads": {
            "name": "TikTok Ads",
            "type": "social_video",
            "min_budget_daily": 20,
            "best_for": ["viral", "trending", "young_demo"],
            "targeting_options": ["interest", "behavior", "lookalike"],
            "metrics_tracked": ["views", "engagement_rate", "cpm", "ctr"],
        },
        "meta_ads": {
            "name": "Meta Ads (FB+IG)",
            "type": "social_mixed",
            "min_budget_daily": 15,
            "best_for": ["detailed_targeting", "retargeting", "conversion"],
            "targeting_options": ["demographic", "interest", "custom_audience", "lookalike"],
            "metrics_tracked": ["impressions", "ctr", "cpc", "conversion_rate"],
        },
        "google_ads": {
            "name": "Google Ads",
            "type": "search_display",
            "min_budget_daily": 25,
            "best_for": ["high_intent", "b2b", "local_business"],
            "targeting_options": ["keyword", "topic", "placement", "remarketing"],
            "metrics_tracked": ["clicks", "impressions", "ctr", "conversions", "quality_score"],
        },
        "pinterest": {
            "name": "Pinterest Ads",
            "type": "visual_discovery",
            "min_budget_daily": 10,
            "best_for": ["inspiration", "design", "diy"],
            "targeting_options": ["interest", "keyword", "actalike"],
            "metrics_tracked": ["saves", "clicks", "ctr", "outbound_clicks"],
        },
        "seo_blog": {
            "name": "SEO Blog",
            "type": "organic_content",
            "min_budget_daily": 0,
            "best_for": ["long_tail_traffic", "authority", "educational"],
            "targeting_options": ["keyword", "topic_cluster"],
            "metrics_tracked": ["organic_traffic", "ranking", "bounce_rate", "time_on_page"],
        },
        "whatsapp": {
            "name": "WhatsApp Broadcast",
            "type": "messaging",
            "min_budget_daily": 0,
            "best_for": ["existing_contacts", "warm_leads", "retention"],
            "targeting_options": ["list_segment", "engagement_score"],
            "metrics_tracked": ["delivery_rate", "read_rate", "reply_rate", "conversion"],
        },
    }

    @staticmethod
    def create_distribution_plan(product: str, target: str, country: str,
                                 budget_total: float = 1000) -> dict:
        """创建多平台分发计划

        Args:
            product: 产品描述
            target: 目标客户
            country: 国家
            budget_total: 总预算

        Returns:
            dict: {platforms, total_budget, duration_days, schedule}
        """
        # 根据产品和国家选择平台
        selected_platforms = ChannelDistributor._select_platforms(product, country)

        # 分配预算
        budget_split = ChannelDistributor._allocate_budget(
            selected_platforms, budget_total
        )

        # 生成时间表
        schedule = ChannelDistributor._generate_schedule(
            selected_platforms, budget_split
        )

        return {
            "product": product,
            "target": target,
            "country": country,
            "total_budget": budget_total,
            "duration_days": 30,
            "platforms": budget_split,
            "schedule": schedule,
            "ab_test_plan": ChannelDistributor._generate_ab_test_plan(selected_platforms),
        }

    @staticmethod
    def _select_platforms(product: str, country: str) -> list:
        """自动选择最佳平台组合"""
        product_lower = product.lower()
        country_upper = country.upper() if country else ""

        visual = any(k in product_lower for k in ["sign", "led", "light", "display"])
        luxury_markets = ["AE", "SA", "QA", "KW"]
        western_markets = ["US", "CA", "GB", "AU"]

        platforms = []

        if visual:
            platforms.extend(["tiktok_ads", "meta_ads", "pinterest"])
        if country_upper in western_markets:
            platforms.append("google_ads")
        if country_upper in luxury_markets:
            platforms.extend(["meta_ads", "pinterest"])
        platforms.append("seo_blog")
        platforms.append("whatsapp")

        # 去重
        seen = set()
        return [p for p in platforms if not (p in seen or seen.add(p))]

    @staticmethod
    def _allocate_budget(platforms: list, total_budget: float) -> list:
        """智能分配预算到各平台"""
        base_allocations = {
            "tiktok_ads": 0.25,
            "meta_ads": 0.30,
            "google_ads": 0.25,
            "pinterest": 0.10,
            "seo_blog": 0.05,
            "whatsapp": 0.05,
        }

        # 归一化
        selected = [p for p in platforms if p in base_allocations]
        total_weight = sum(base_allocations[p] for p in selected)

        results = []
        for platform in selected:
            weight = base_allocations[platform] / total_weight
            budget = round(total_budget * weight, 2)
            results.append({
                "platform": platform,
                "name": ChannelDistributor.PLATFORMS.get(platform, {}).get("name", platform),
                "budget": budget,
                "budget_pct": round(weight * 100, 1),
                "daily_budget": round(budget / 30, 2),
            })

        return results

    @staticmethod
    def _generate_schedule(platforms: list, budget_split: list) -> list:
        """生成投放时间表"""
        schedule = []
        for p in budget_split:
            schedule.append({
                "platform": p["platform"],
                "phase_1_days_1_7": "test",
                "phase_2_days_8_14": "optimize",
                "phase_3_days_15_30": "scale",
                "total_budget": p["budget"],
            })
        return schedule

    @staticmethod
    def _generate_ab_test_plan(platforms: list) -> list:
        """生成A/B测试计划"""
        tests = []
        for platform in platforms[:3]:  # 最多3个平台做A/B测试
            tests.append({
                "platform": platform,
                "test_variables": ["headline", "image", "cta", "audience"],
                "test_duration_days": 7,
                "min_confidence": 0.95,
                "winner_selection": "ctr_and_conversion",
            })
        return tests

    @staticmethod
    def get_performance_report(results: list) -> dict:
        """分析投放效果报告"""
        total_spent = sum(r.get("spent", 0) for r in results)
        total_leads = sum(r.get("leads", 0) for r in results)
        total_conversions = sum(r.get("conversions", 0) for r in results)

        return {
            "total_spent": total_spent,
            "total_leads": total_leads,
            "total_conversions": total_conversions,
            "average_cpl": round(total_spent / total_leads, 2) if total_leads > 0 else 0,
            "average_cpa": round(total_spent / total_conversions, 2) if total_conversions > 0 else 0,
            "best_platform": max(results, key=lambda r: r.get("conversions", 0)).get("platform", "")
            if results else "",
            "platforms": results,
        }


# 快捷入口
distributor = ChannelDistributor()


def create_plan(product: str, target: str, country: str, budget: float = 1000) -> dict:
    return ChannelDistributor.create_distribution_plan(product, target, country, budget)
