"""Product Expander — 产品自动扩展系统

系统自动发现"能卖什么"。
当前产品：发光字 → 自动扩展：亚克力家具 / 酒店灯箱 / 商场导视系统 / 店铺装修套餐
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class ProductExpander:
    """产品扩展系统 — 从单一产品到全店解决方案"""

    # 产品矩阵定义
    PRODUCT_MATRIX = {
        "luminous_sign": {
            "name": "LED Luminous Sign",
            "category": "signage",
            "base_price_range": (200, 800),
            "extensions": [
                {"product_id": "led_neon_flex", "name": "LED Neon Flex Sign",
                 "description": "Flexible neon-style LED signs", "price_multiplier": 0.8,
                 "difficulty": "easy", "related_to": ["restaurant", "retail"]},
                {"product_id": "lightbox", "name": "Lightbox Sign",
                 "description": "Illuminated lightbox for storefronts", "price_multiplier": 1.2,
                 "difficulty": "easy", "related_to": ["pharmacy", "retail", "hospitality"]},
                {"product_id": "3d_letter", "name": "3D Acrylic Letter Sign",
                 "description": "Premium 3D acrylic lettering", "price_multiplier": 1.5,
                 "difficulty": "medium", "related_to": ["corporate", "luxury"]},
                {"product_id": "pylon_sign", "name": "Pylon/Monument Sign",
                 "description": "Large freestanding signage", "price_multiplier": 3.0,
                 "difficulty": "hard", "related_to": ["hotel", "mall", "business_park"]},
            ],
        },
        "led_display": {
            "name": "LED Display Screen",
            "category": "digital_signage",
            "base_price_range": (500, 3000),
            "extensions": [
                {"product_id": "video_wall", "name": "Video Wall",
                 "description": "Multi-screen video wall installation", "price_multiplier": 4.0,
                 "difficulty": "hard", "related_to": ["conference", "event", "control_room"]},
                {"product_id": "menu_board", "name": "Digital Menu Board",
                 "description": "Dynamic restaurant menu display", "price_multiplier": 1.5,
                 "difficulty": "medium", "related_to": ["restaurant", "fast_food", "cafe"]},
                {"product_id": "window_display", "name": "Interactive Window Display",
                 "description": "Engaging storefront window display", "price_multiplier": 2.0,
                 "difficulty": "hard", "related_to": ["retail", "showroom"]},
            ],
        },
        "acrylic_furniture": {
            "name": "Acrylic Furniture",
            "category": "furniture",
            "base_price_range": (100, 500),
            "extensions": [
                {"product_id": "acrylic_shelf", "name": "Acrylic Display Shelf",
                 "description": "Modern acrylic shelving units", "price_multiplier": 0.8,
                 "difficulty": "easy", "related_to": ["retail", "exhibition"]},
                {"product_id": "acrylic_counter", "name": "Acrylic Counter/Desk",
                 "description": "Contemporary acrylic service counters", "price_multiplier": 2.0,
                 "difficulty": "medium", "related_to": ["reception", "hotel", "office"]},
                {"product_id": "acrylic_display", "name": "Acrylic Product Display",
                 "description": "Custom acrylic product display stands", "price_multiplier": 0.6,
                 "difficulty": "easy", "related_to": ["retail", "museum", "exhibition"]},
            ],
        },
        "wayfinding": {
            "name": "Wayfinding System",
            "category": "signage",
            "base_price_range": (300, 2000),
            "extensions": [
                {"product_id": "directory_sign", "name": "Directory Sign",
                 "description": "Building directory and directional signs", "price_multiplier": 1.5,
                 "difficulty": "medium", "related_to": ["office", "mall", "hospital"]},
                {"product_id": "room_sign", "name": "Room Number/Label Sign",
                 "description": "Professional room identification", "price_multiplier": 0.3,
                 "difficulty": "easy", "related_to": ["hotel", "office", "hospital"]},
                {"product_id": "floor_direction", "name": "Floor Directional Sign",
                 "description": "Floor-by-floor wayfinding system", "price_multiplier": 0.8,
                 "difficulty": "medium", "related_to": ["mall", "parking", "airport"]},
            ],
        },
    }

    @staticmethod
    def expand(current_product: str, industry: str = "") -> dict:
        """从当前产品扩展出产品矩阵

        Args:
            current_product: 当前产品ID
            industry: 客户行业

        Returns:
            dict: {current, extensions: [...], bundles: [...], upsells: [...]}
        """
        base = ProductExpander.PRODUCT_MATRIX.get(current_product)
        if not base:
            return {"error": f"Product '{current_product}' not found in matrix"}

        extensions = base.get("extensions", [])
        if industry:
            industry_lower = industry.lower()
            extensions = [
                e for e in extensions
                if any(r in industry_lower for r in e.get("related_to", []))
            ] or extensions

        # 生成套餐组合
        bundles = ProductExpander._suggest_bundles(base, extensions)
        upsells = ProductExpander._suggest_upsells(base, extensions)

        return {
            "current_product": current_product,
            "current_product_name": base["name"],
            "category": base["category"],
            "base_price_range": base["base_price_range"],
            "extensions": extensions,
            "total_extensions": len(extensions),
            "recommended_bundles": bundles,
            "upsell_opportunities": upsells,
        }

    @staticmethod
    def _suggest_bundles(base: dict, extensions: list) -> list:
        """生成套餐推荐"""
        if not extensions:
            return []

        main_name = base["name"]
        bundles = []

        if len(extensions) >= 2:
            bundles.append({
                "name": f"Complete {main_name} Package",
                "items": [extensions[0]["product_id"], extensions[1]["product_id"]],
                "discount": 0.10,
                "description": f"Save 10% with this bundle",
                "best_for": "new_business_setup",
            })

        if len(extensions) >= 1:
            bundles.append({
                "name": f"{main_name} + Installation",
                "items": [extensions[0]["product_id"]],
                "discount": 0.05,
                "description": "Professional installation included",
                "best_for": "first_time_buyer",
            })

        return bundles

    @staticmethod
    def _suggest_upsells(base: dict, extensions: list) -> list:
        """生成向上销售推荐"""
        upsells = []
        for ext in extensions:
            if ext.get("difficulty") in ("medium", "hard") and ext.get("price_multiplier", 1) > 1.5:
                upsells.append({
                    "from": base["name"],
                    "to": ext["name"],
                    "price_increase": f"{int((ext['price_multiplier'] - 1) * 100)}%",
                    "value_proposition": ext["description"],
                })
        return upsells[:3]

    @staticmethod
    def get_all_categories() -> list:
        """获取所有产品类别"""
        return [
            {"id": pid, "name": p["name"], "category": p["category"],
             "extensions_count": len(p.get("extensions", []))}
            for pid, p in ProductExpander.PRODUCT_MATRIX.items()
        ]


# 快捷入口
expander = ProductExpander()


def expand_product(current_product: str, industry: str = "") -> dict:
    return ProductExpander.expand(current_product, industry)
