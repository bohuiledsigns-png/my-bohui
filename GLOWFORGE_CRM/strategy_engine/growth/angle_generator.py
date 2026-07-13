"""Creative Angle Generator — 广告角度生成器

自动生成「怎么打广告」的策略角度。
不是随机组合，而是基于市场偏好 × 产品类型 × 历史数据。

角度五大类:
  1. Luxury — 高端定位
  2. Problem Solving — 解决问题
  3. Price Comparison — 价格对比
  4. Fast Shipping — 快速交付
  5. Emotional Appeal — 情感共鸣
"""
import logging
from copy import deepcopy

logger = logging.getLogger("growth.angle_generator")

# ── 角度模板库 ──────────────────────────────────────────────
ANGLE_LIBRARY = [
    # ── Luxury 高端定位 ──
    {
        "id": "luxury_premium",
        "name": "Luxury Premium",
        "category": "luxury",
        "hook": "Premium {product} for discerning businesses",
        "description": "强调高端材质、意式设计、 luxury 质感",
        "conversion_style": "premium",
        "suitable_markets": ["US", "AE", "JP", "GB", "CA", "AU", "SA", "QA", "KW"],
        "suitable_products": ["led_letter", "cabinet", "mirror", "acrylic"],
        "roi_modifier": 1.15,
    },
    {
        "id": "luxury_italian_design",
        "name": "Italian Design Premium",
        "category": "luxury",
        "hook": "Italian-designed {product} — direct from factory",
        "description": "意式设计概念 + 工厂直供",
        "conversion_style": "premium",
        "suitable_markets": ["US", "GB", "EU", "AE", "JP"],
        "suitable_products": ["cabinet", "mirror", "led_letter"],
        "roi_modifier": 1.10,
    },
    # ── Problem Solving 解决问题 ──
    {
        "id": "problem_visibility",
        "name": "Visibility Solution",
        "category": "problem_solving",
        "hook": "Make your business visible 24/7 with {product}",
        "description": "强调招牌/展示的可见性价值",
        "conversion_style": "solution",
        "suitable_markets": ["all"],
        "suitable_products": ["led_letter", "sign", "light_box"],
        "roi_modifier": 1.05,
    },
    {
        "id": "problem_quality",
        "name": "Quality Guarantee",
        "category": "problem_solving",
        "hook": "Stop replacing cheap {product} every year",
        "description": "劣质产品对比，强调工厂直供品质保证",
        "conversion_style": "pain_point",
        "suitable_markets": ["all"],
        "suitable_products": ["all"],
        "roi_modifier": 1.00,
    },
    # ── Price Comparison 价格对比 ──
    {
        "id": "price_factory_direct",
        "name": "Factory Direct Price",
        "category": "price_comparison",
        "hook": "Factory price — not retail. {product} at wholesale",
        "description": "工厂直供、去掉中间商差价",
        "conversion_style": "value",
        "suitable_markets": ["US", "EU", "GB", "AU", "CA", "AE", "SA"],
        "suitable_products": ["led_letter", "sign", "light_box", "acrylic"],
        "roi_modifier": 1.10,
    },
    {
        "id": "price_bulk_discount",
        "name": "Bulk Discount Advantage",
        "category": "price_comparison",
        "hook": "The more you order, the less you pay per unit",
        "description": "批量采购优惠，适合 B2B 客户",
        "conversion_style": "value",
        "suitable_markets": ["US", "AE", "SA", "GB", "AU", "CA"],
        "suitable_products": ["all"],
        "roi_modifier": 1.05,
    },
    # ── Fast Shipping 快速交付 ──
    {
        "id": "fast_express",
        "name": "Fast Express Delivery",
        "category": "fast_shipping",
        "hook": "Express delivery — {product} arrives in days, not months",
        "description": "快速交付保障，减轻客户等待焦虑",
        "conversion_style": "urgency",
        "suitable_markets": ["US", "GB", "AE", "EU", "JP", "SG"],
        "suitable_products": ["led_letter", "light_box", "small_sign"],
        "roi_modifier": 1.08,
    },
    {
        "id": "fast_logistics",
        "name": "Global Logistics Ready",
        "category": "fast_shipping",
        "hook": "Global stock ready — {product} shipped within 48 hours",
        "description": "全球仓储 + 48小时发货",
        "conversion_style": "urgency",
        "suitable_markets": ["US", "GB", "AE", "DE", "FR", "SG", "JP"],
        "suitable_products": ["led_letter", "sign", "light_box"],
        "roi_modifier": 1.12,
    },
    # ── Emotional Appeal 情感共鸣 ──
    {
        "id": "emotional_brand",
        "name": "Brand Story Emotional",
        "category": "emotional_appeal",
        "hook": "Your brand deserves {product} that tells your story",
        "description": "品牌故事驱动，情感连接",
        "conversion_style": "storytelling",
        "suitable_markets": ["US", "GB", "AU", "CA", "JP", "EU"],
        "suitable_products": ["cabinet", "mirror", "led_letter", "acrylic"],
        "roi_modifier": 1.05,
    },
    {
        "id": "emotional_pride",
        "name": "Business Pride",
        "category": "emotional_appeal",
        "hook": "Your storefront is your handshake — make it unforgettable",
        "description": "店主自豪感、门面即名片",
        "conversion_style": "storytelling",
        "suitable_markets": ["all"],
        "suitable_products": ["all"],
        "roi_modifier": 1.02,
    },
]

# ── 市场角度偏好权重 ──
# 不同市场对不同角度的响应率差异
MARKET_ANGLE_PREFERENCE = {
    "US": {"luxury": 0.20, "problem_solving": 0.15, "price_comparison": 0.25, "fast_shipping": 0.25, "emotional_appeal": 0.15},
    "AE": {"luxury": 0.35, "problem_solving": 0.10, "price_comparison": 0.15, "fast_shipping": 0.25, "emotional_appeal": 0.15},
    "GB": {"luxury": 0.25, "problem_solving": 0.20, "price_comparison": 0.20, "fast_shipping": 0.20, "emotional_appeal": 0.15},
    "EU": {"luxury": 0.20, "problem_solving": 0.20, "price_comparison": 0.25, "fast_shipping": 0.15, "emotional_appeal": 0.20},
    "JP": {"luxury": 0.30, "problem_solving": 0.15, "price_comparison": 0.15, "fast_shipping": 0.15, "emotional_appeal": 0.25},
    "SA": {"luxury": 0.30, "problem_solving": 0.10, "price_comparison": 0.25, "fast_shipping": 0.25, "emotional_appeal": 0.10},
    "default": {"luxury": 0.20, "problem_solving": 0.20, "price_comparison": 0.20, "fast_shipping": 0.20, "emotional_appeal": 0.20},
}

# 产品类别 → 角度匹配加成
PRODUCT_ANGLE_BOOST = {
    "led_letter": {"luxury": 0.05, "fast_shipping": 0.08},
    "cabinet": {"luxury": 0.10, "emotional_appeal": 0.05},
    "mirror": {"luxury": 0.12, "emotional_appeal": 0.08},
    "acrylic": {"luxury": 0.08, "price_comparison": 0.05},
    "sign": {"fast_shipping": 0.05, "price_comparison": 0.05},
    "light_box": {"fast_shipping": 0.05, "price_comparison": 0.05},
}


class CreativeAngleGenerator:
    """广告角度生成器"""

    @staticmethod
    def generate_angles(market=None, product=None, limit=5):
        """为指定市场和产品生成广告角度

        参数:
            market: ISO 国家代码，为 None 则返回通用角度
            product: 产品类别，为 None 则返回所有产品适用角度
            limit: 返回角度数量上限

        返回:
            dict: { angles: [{ id, name, hook, description, style, score }] }
        """
        scored = []
        for angle in ANGLE_LIBRARY:
            # 过滤市场适用性
            if market and "all" not in angle["suitable_markets"]:
                if market not in angle["suitable_markets"]:
                    continue

            # 过滤产品适用性
            if product and "all" not in angle["suitable_products"]:
                if product not in angle["suitable_products"]:
                    continue

            # 基础分
            score = 1.0

            # 市场偏好加成
            pref = MARKET_ANGLE_PREFERENCE.get(market, MARKET_ANGLE_PREFERENCE["default"])
            category = angle["category"]
            score += pref.get(category, 0)

            # 产品加成
            if product:
                boosts = PRODUCT_ANGLE_BOOST.get(product, {})
                score += boosts.get(category, 0)

            # ROI 修正
            score *= angle["roi_modifier"]

            scored.append({
                "id": angle["id"],
                "name": angle["name"],
                "category": angle["category"],
                "hook": angle["hook"].format(product=product or "product"),
                "description": angle["description"],
                "conversion_style": angle["conversion_style"],
                "score": round(score, 3),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        return {
            "angles": scored[:limit],
            "total_candidates": len(scored),
            "market": market or "all",
            "product": product or "all",
        }

    @staticmethod
    def get_best_angle(market, product, historical_data=None):
        """获取指定上下文中表现最好的角度

        结合历史表现和理论评分做加权选择。
        """
        angles = CreativeAngleGenerator.generate_angles(
            market=market, product=product, limit=10
        )

        best = None
        best_score = -1

        for a in angles["angles"]:
            final_score = a["score"]

            # 如果有历史数据，加权修正
            if historical_data:
                hist = historical_data.get(a["id"], {})
                hist_roi = hist.get("avg_roi", 0)
                samples = hist.get("samples", 0)
                if samples >= 3:
                    # 历史权重 = min(样本数 / 20, 0.5)
                    hist_weight = min(samples / 20, 0.5)
                    # 归一化 ROI 到 [0.5, 2.0] 范围
                    normalized_roi = min(max(hist_roi / 2.0, 0.5), 2.0)
                    final_score = final_score * (1 - hist_weight) + normalized_roi * hist_weight

            if final_score > best_score:
                best_score = final_score
                best = {**a, "final_score": round(final_score, 3)}

        return {
            "best_angle": best,
            "all_candidates": angles["angles"],
        }

    @staticmethod
    def get_all_categories():
        """获取所有角度分类"""
        cats = {}
        for angle in ANGLE_LIBRARY:
            cat = angle["category"]
            if cat not in cats:
                cats[cat] = []
            cats[cat].append(angle["id"])
        return {
            "categories": [
                {"name": k, "angles": v, "count": len(v)}
                for k, v in cats.items()
            ],
            "total_angles": len(ANGLE_LIBRARY),
        }

    @staticmethod
    def format_angle_for_ad(angle, brand_name="GLOWFORGE"):
        """将角度格式化为广告文案片段"""
        return {
            "headline": angle["hook"],
            "description": angle["description"],
            "call_to_action": CreativeAngleGenerator._cta_for_style(
                angle["conversion_style"]
            ),
            "brand": brand_name,
        }

    @staticmethod
    def _cta_for_style(style):
        ctas = {
            "premium": "Get Premium Quote",
            "solution": "Solve Your Needs",
            "pain_point": "Upgrade Now",
            "value": "Get Wholesale Price",
            "urgency": "Order Now — Limited Stock",
            "storytelling": "Tell Your Brand Story",
        }
        return ctas.get(style, "Contact Us Today")
