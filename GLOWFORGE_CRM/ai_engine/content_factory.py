"""Content Factory — 自动内容生产工厂

1个产品 = 无限内容资产。
输入：门店照片 + 招牌效果
输出：TikTok视频 / Before-After图 / 广告Banner / Instagram Reel / YouTube Shorts
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class ContentFactory:
    """内容工厂 — 自动生成爆款营销内容"""

    # 内容模板
    CONTENT_TEMPLATES = {
        "tiktok_video": {
            "type": "short_video",
            "platform": "tiktok",
            "aspect_ratio": "9:16",
            "max_duration": 35,
            "structure": ["hook_3sec", "showcase_15sec", "benefit_10sec", "cta_5sec"],
            "style": "trendy_fast_paced",
        },
        "instagram_reel": {
            "type": "short_video",
            "platform": "instagram",
            "aspect_ratio": "9:16",
            "max_duration": 30,
            "structure": ["hook_3sec", "visual_15sec", "text_overlay_8sec", "cta_4sec"],
            "style": "polished_aesthetic",
        },
        "youtube_shorts": {
            "type": "short_video",
            "platform": "youtube",
            "aspect_ratio": "9:16",
            "max_duration": 45,
            "structure": ["intro_5sec", "process_20sec", "result_15sec", "cta_5sec"],
            "style": "informative_engaging",
        },
        "before_after": {
            "type": "image_comparison",
            "platform": "all",
            "aspect_ratio": "1:1",
            "style": "dramatic_contrast",
            "elements": ["left_before", "right_after", "center_divider", "caption"],
        },
        "ad_banner": {
            "type": "static_image",
            "platform": "facebook_google",
            "aspect_ratio": "1.91:1",
            "style": "clean_professional",
            "elements": ["product_photo", "headline", "cta_button", "logo"],
        },
        "testimonial_card": {
            "type": "quote_image",
            "platform": "all",
            "aspect_ratio": "1:1",
            "style": "trust_building",
            "elements": ["customer_photo", "quote_text", "rating_stars", "company_logo"],
        },
        "product_carousel": {
            "type": "multi_image",
            "platform": "instagram_linkedin",
            "aspect_ratio": "1:1",
            "slides": 5,
            "style": "showcase_journey",
            "structure": ["problem_slide", "solution_slide", "detail_slide", "result_slide", "cta_slide"],
        },
    }

    # 营销角度
    ANGLES = [
        "before_after_transformation",
        "customer_testimonial",
        "behind_the_scenes",
        "quality_craftsmanship",
        "roi_calculation",
        "comparison_vs_competitors",
        "installation_process",
        "design_process",
        "material_quality",
        "team_expertise",
    ]

    @staticmethod
    def generate_content_plan(product: str, target: str, country: str,
                               count: int = 10) -> list:
        """生成内容计划

        Args:
            product: 产品描述
            target: 目标客户
            country: 目标国家
            count: 内容数量

        Returns:
            list: [{type, title, platform, structure, ...}]
        """
        plans = []
        template_keys = list(ContentFactory.CONTENT_TEMPLATES.keys())
        angles = ContentFactory.ANGLES

        for i in range(count):
            template_key = template_keys[i % len(template_keys)]
            template = ContentFactory.CONTENT_TEMPLATES[template_key]
            angle = angles[i % len(angles)]

            plans.append({
                "id": i + 1,
                "template": template_key,
                "type": template["type"],
                "platform": template["platform"],
                "style": template["style"],
                "angle": angle,
                "title": ContentFactory._generate_title(template_key, angle, product, target, country),
                "structure": template.get("structure", []),
                "aspect_ratio": template["aspect_ratio"],
            })

        return plans

    @staticmethod
    def _generate_title(template: str, angle: str, product: str,
                         target: str, country: str) -> str:
        """根据模板和角度生成标题"""
        titles_map = {
            "before_after": f"See the transformation: {product} for {target} in {country}",
            "customer_testimonial": f"{target} love their new {product}",
            "behind_the_scenes": f"How we make premium {product}",
            "quality_craftsmanship": f"The craftsmanship behind our {product}",
            "roi_calculation": f"How {product} pays for itself in 3 months",
            "comparison_vs_competitors": f"Our {product} vs competitors: the truth",
            "installation_process": f"Watch us install a {product} in 24 hours",
            "design_process": f"From sketch to stunning: {product} design process",
            "material_quality": f"Why we use only premium materials for {product}",
            "team_expertise": f"Meet the team behind your {product}",
        }

        for key, title in titles_map.items():
            if key in angle or key in template:
                return title

        return f"Amazing {product} for {target} in {country}"

    @staticmethod
    def get_content_script(template: str, angle: str, product: str,
                           target: str, country: str) -> dict:
        """生成具体内容的脚本

        Returns:
            dict: {template, script_sections, captions, hashtags, call_to_action}
        """
        template_config = ContentFactory.CONTENT_TEMPLATES.get(template, {})

        # 生成 hashtags
        hashtags = [
            f"#{product.replace(' ', '')}",
            f"#{country}Business",
            f"#{target.replace(' ', '')}",
            "#Signage",
            "#LEDSigns",
            "#BusinessGrowth",
            "#Storefront",
            "#SmallBusiness",
        ]

        # 生成 CTA
        ctas = [
            "DM for free quote",
            "Link in bio to order",
            "Contact us today",
            "WhatsApp us for consultation",
        ]

        return {
            "template": template,
            "type": template_config.get("type", template),
            "platform": template_config.get("platform", "all"),
            "angle": angle,
            "structure": template_config.get("structure", []),
            "suggested_hashtags": hashtags,
            "suggested_cta": ctas[hash(angle) % len(ctas)],
            "target_audience": f"{target} in {country}",
            "primary_message": f"Premium {product} for your {country} business",
        }

    @staticmethod
    def batch_generate(product: str, target: str, country: str,
                       count: int = 30) -> dict:
        """批量生成内容资产

        Args:
            product: 产品
            target: 目标客户
            country: 国家
            count: 内容数量

        Returns:
            dict: {content_plan, scripts, total_count, platforms_summary}
        """
        plans = ContentFactory.generate_content_plan(product, target, country, count)

        scripts = []
        for p in plans:
            script = ContentFactory.get_content_script(
                p["template"], p["angle"], product, target, country
            )
            scripts.append(script)

        # 平台统计
        platforms = {}
        for s in scripts:
            plt = s["platform"]
            if plt not in platforms:
                platforms[plt] = 0
            platforms[plt] += 1

        return {
            "product": product,
            "target": target,
            "country": country,
            "total_count": count,
            "platforms": platforms,
            "hashtags": list(set(h for s in scripts for h in s["suggested_hashtags"])),
            "content_plan": plans,
            "scripts": scripts,
        }


# 快捷入口
factory = ContentFactory()


def plan_content(product: str, target: str, country: str, count: int = 30) -> dict:
    return ContentFactory.batch_generate(product, target, country, count)
