"""Acquisition Engine — 自动获客系统

不再等客户，而是"制造客户"。
AI自动生成：TikTok视频、Instagram广告、Google广告、SEO页面、冷邮件、WhatsApp群引流。

输入：product + target + country
输出：30条短视频 + 10条广告 + 5个落地页 + 3个SEO页面
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class AcquisitionEngine:
    """自动获客系统 — 从被动等待到主动制造客户"""

    # 获客渠道配置
    CHANNELS = {
        "tiktok": {
            "name": "TikTok",
            "content_type": "short_video",
            "ideal_length_sec": 30,
            "cost_per_lead": "low",
            "best_for": ["visual_products", "before_after", "showcase"],
            "format": "9:16 vertical video",
        },
        "instagram": {
            "name": "Instagram",
            "content_type": "image_carousel",
            "ideal_length_sec": 0,
            "cost_per_lead": "medium",
            "best_for": ["brand_showcase", "before_after", "testimonial"],
            "format": "1:1 square or 4:5 portrait",
        },
        "google_ads": {
            "name": "Google Ads",
            "content_type": "search_ad",
            "ideal_length_sec": 0,
            "cost_per_lead": "high",
            "best_for": ["intent_based", "high_purchase_intent"],
            "format": "text + headline",
        },
        "seo_blog": {
            "name": "SEO Blog",
            "content_type": "article",
            "ideal_length_sec": 0,
            "cost_per_lead": "very_low",
            "best_for": ["long_tail_keywords", "educational"],
            "format": "1500-2000 word article",
        },
        "cold_email": {
            "name": "Cold Email",
            "content_type": "email",
            "ideal_length_sec": 0,
            "cost_per_lead": "low",
            "best_for": ["b2b", "high_value"],
            "format": "short personalized email",
        },
        "whatsapp_broadcast": {
            "name": "WhatsApp Broadcast",
            "content_type": "message",
            "ideal_length_sec": 0,
            "cost_per_lead": "very_low",
            "best_for": ["existing_contacts", "referrals"],
            "format": "short promotional message",
        },
    }

    @staticmethod
    def generate_campaign(product: str, target: str, country: str,
                          channels: list = None) -> dict:
        """生成多渠道获客活动方案

        Args:
            product: 产品描述 (e.g. "luminous sign")
            target: 目标客户 (e.g. "restaurant owners")
            country: 目标国家
            channels: 指定渠道，None=自动选择最佳渠道

        Returns:
            dict: {campaign_plan, channels, total_content_items, ...}
        """
        if channels is None:
            channels = AcquisitionEngine._select_best_channels(product, country)

        campaign = {
            "product": product,
            "target": target,
            "country": country,
            "generated_at": datetime.now().isoformat(),
            "channels": [],
            "total_content_items": 0,
        }

        for channel in channels:
            channel_config = AcquisitionEngine.CHANNELS.get(channel, {})
            content_items = AcquisitionEngine._generate_content_plan(
                channel, product, target, country
            )
            campaign["channels"].append({
                "channel": channel,
                "channel_name": channel_config.get("name", channel),
                "content_type": channel_config.get("content_type", ""),
                "format": channel_config.get("format", ""),
                "content_items": content_items,
                "count": len(content_items),
            })
            campaign["total_content_items"] += len(content_items)

        return campaign

    @staticmethod
    def _select_best_channels(product: str, country: str) -> list:
        """根据产品和目标自动选择最佳渠道"""
        product_lower = product.lower()
        country_upper = country.upper() if country else ""

        # 视觉产品优先视频渠道
        visual_keywords = ["sign", "led", "light", "display", "illuminated", "neon"]
        is_visual = any(k in product_lower for k in visual_keywords)

        # 高价值市场优先多渠道
        high_value_markets = ["AE", "SA", "US", "CA", "GB", "DE"]

        if is_visual and country_upper in high_value_markets:
            return ["tiktok", "instagram", "google_ads", "seo_blog", "whatsapp_broadcast"]
        elif is_visual:
            return ["tiktok", "instagram", "seo_blog"]
        elif country_upper in high_value_markets:
            return ["google_ads", "cold_email", "seo_blog"]
        else:
            return ["seo_blog", "whatsapp_broadcast"]

    @staticmethod
    def _generate_content_plan(channel: str, product: str,
                                target: str, country: str) -> list:
        """生成某个渠道的内容计划"""
        channel = channel.lower()

        if channel == "tiktok":
            return [
                {"type": "product_showcase", "title": f"Amazing {product} transformation",
                 "duration_sec": 30, "hook": f"Restaurant owners {country} NEED this"},
                {"type": "before_after", "title": "Before vs After: Storefront upgrade",
                 "duration_sec": 25, "hook": "See the difference"},
                {"type": "installation", "title": "How we install a premium sign",
                 "duration_sec": 35, "hook": "Behind the scenes"},
                {"type": "customer_reaction", "title": "Customer sees their new sign for first time",
                 "duration_sec": 20, "hook": "Priceless reaction"},
                {"type": "fast_facts", "title": f"5 reasons {target} choose us",
                 "duration_sec": 30, "hook": "Number 3 will surprise you"},
            ]

        elif channel == "instagram":
            return [
                {"type": "carousel", "title": f"10 stunning {product} installations in {country}",
                 "slides": 10, "format": "carousel"},
                {"type": "before_after", "title": "Storefront glow-up",
                 "format": "side_by_side"},
                {"type": "testimonial", "title": f"{target} love their new sign",
                 "format": "quote_card"},
            ]

        elif channel == "google_ads":
            return [
                {"type": "search_ad", "headline": f"Custom {product} for {target} in {country}",
                 "description": f"Premium quality, fast delivery. Get a free quote today."},
                {"type": "search_ad", "headline": f"Best {product} for your business",
                 "description": f"Stand out from competition. Durable LED signs since 2010."},
            ]

        elif channel == "seo_blog":
            return [
                {"type": "guide", "title": f"Complete guide to choosing {product} for your business",
                 "target_keywords": [f"buy {product}", f"{product} for {target}", f"custom {product} {country}"]},
                {"type": "comparison", "title": f"{product} vs traditional signage: ROI comparison",
                 "target_keywords": [f"{product} benefits", f"LED sign ROI"]},
            ]

        elif channel == "cold_email":
            return [
                {"type": "intro_email", "subject": f"Help your {target} business stand out",
                 "tone": "professional", "follow_up_days": 3},
            ]

        elif channel == "whatsapp_broadcast":
            return [
                {"type": "promo_message", "text": f"Special offer on {product} this month!",
                 "include_image": True, "call_to_action": "Reply for free quote"},
            ]

        return []

    @staticmethod
    def estimate_budget(channels: list = None, duration_days: int = 30) -> dict:
        """估算获客预算

        Args:
            channels: 渠道列表
            duration_days: 投放天数

        Returns:
            dict: {total_budget, channel_breakdown, estimated_leads}
        """
        channels = channels or []
        daily_budgets = {
            "tiktok": 50,
            "instagram": 80,
            "google_ads": 100,
            "seo_blog": 20,
            "cold_email": 30,
            "whatsapp_broadcast": 10,
        }

        leads_per_dollar = {
            "tiktok": 0.5,
            "instagram": 0.3,
            "google_ads": 0.2,
            "seo_blog": 0.1,
            "cold_email": 0.4,
            "whatsapp_broadcast": 1.0,
        }

        breakdown = []
        total = 0
        total_leads = 0

        for channel in channels:
            daily = daily_budgets.get(channel, 50)
            budget = daily * duration_days
            leads = int(budget * leads_per_dollar.get(channel, 0.3))
            total += budget
            total_leads += leads
            breakdown.append({
                "channel": channel,
                "daily_budget": daily,
                "total_budget": budget,
                "estimated_leads": leads,
                "cost_per_lead": round(budget / leads, 2) if leads > 0 else 0,
            })

        return {
            "duration_days": duration_days,
            "total_budget": total,
            "estimated_total_leads": total_leads,
            "avg_cost_per_lead": round(total / total_leads, 2) if total_leads > 0 else 0,
            "channel_breakdown": breakdown,
        }


# 快捷入口
engine = AcquisitionEngine()


def plan_campaign(product: str, target: str, country: str) -> dict:
    return AcquisitionEngine.generate_campaign(product, target, country)


def estimate_budget(channels: list = None, duration_days: int = 30) -> dict:
    if channels is None:
        channels = list(AcquisitionEngine.CHANNELS.keys())
    return AcquisitionEngine.estimate_budget(channels, duration_days)
