"""Business Clone Engine — 商业复制系统

找到成功模型 → 自动复制到新市场/新产品。
成功不是优化，而是"无限复制"。

例：US餐厅招牌转化率45% → 复制到UK/UAE/Australia餐厅市场
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class BusinessCloneEngine:
    """商业复制系统 — 成功模型无限复制"""

    # 预定义成功模型
    SUCCESS_MODELS = [
        {
            "id": "us_restaurant_sign",
            "source_market": "US",
            "source_industry": "restaurant",
            "product": "luminous_sign",
            "conversion_rate": 45.0,
            "avg_order_value": 680,
            "key_factors": ["fast_quote", "free_design", "before_after_images"],
            "replicable_to": ["GB", "AU", "CA", "AE"],
            "adaptation_needed": {
                "GB": "add_ce_certification",
                "AE": "luxury_positioning",
                "AU": "competitive_pricing",
            },
        },
        {
            "id": "ae_luxury_sign",
            "source_market": "AE",
            "source_industry": "luxury_retail",
            "product": "premium_sign",
            "conversion_rate": 38.0,
            "avg_order_value": 1200,
            "key_factors": ["premium_quality", "vip_service", "prestige_branding"],
            "replicable_to": ["SA", "QA", "KW"],
            "adaptation_needed": {
                "SA": "cultural_tone",
                "QA": "same_as_ae",
            },
        },
        {
            "id": "de_technical_sign",
            "source_market": "DE",
            "source_industry": "industrial",
            "product": "led_display",
            "conversion_rate": 35.0,
            "avg_order_value": 850,
            "key_factors": ["technical_specs", "certifications", "warranty"],
            "replicable_to": ["FR", "NL", "CH"],
            "adaptation_needed": {
                "FR": "design_focus",
                "NL": "direct_communication",
            },
        },
    ]

    @staticmethod
    def find_clone_opportunities(source_market: str = "", min_conversion: float = 30.0) -> list:
        """发现可复制的商业机会

        Args:
            source_market: 源市场代码（空=全部）
            min_conversion: 最低转化率

        Returns:
            list: [{source, target, product, estimated_success_rate, ...}]
        """
        opportunities = []

        for model in BusinessCloneEngine.SUCCESS_MODELS:
            if source_market and model["source_market"] != source_market:
                continue
            if model["conversion_rate"] < min_conversion:
                continue

            for target_market in model["replicable_to"]:
                # 计算预计成功率（基于源市场表现 × 适配系数）
                adaptation = model.get("adaptation_needed", {}).get(target_market, "")
                adaptation_factor = 0.9 if adaptation else 1.0
                estimated_success = round(
                    model["conversion_rate"] * adaptation_factor * 0.85, 1
                )

                opportunities.append({
                    "source_model_id": model["id"],
                    "source_market": model["source_market"],
                    "source_industry": model["source_industry"],
                    "target_market": target_market,
                    "product": model["product"],
                    "source_conversion": model["conversion_rate"],
                    "estimated_success_rate": estimated_success,
                    "estimated_aov": BusinessCloneEngine._estimate_aov(
                        model["avg_order_value"], target_market
                    ),
                    "adaptation_required": bool(adaptation),
                    "adaptation_note": adaptation if adaptation else "standard replication",
                    "priority": "high" if estimated_success >= 30 else "medium",
                })

        opportunities.sort(key=lambda x: x["estimated_success_rate"], reverse=True)
        return opportunities

    @staticmethod
    def _estimate_aov(source_aov: float, target_market: str) -> float:
        """估算目标市场的客单价"""
        market_adjustments = {
            "AE": 1.4, "SA": 1.3, "QA": 1.35,
            "GB": 0.9, "AU": 0.85, "CA": 0.9,
            "FR": 0.85, "DE": 0.95, "NL": 0.9,
            "SG": 0.95, "JP": 0.9,
        }
        adj = market_adjustments.get(target_market, 0.85)
        return round(source_aov * adj, 2)

    @staticmethod
    def create_clone_plan(model_id: str, target_market: str) -> dict:
        """为指定的成功模型生成克隆计划

        Args:
            model_id: 成功模型ID
            target_market: 目标市场

        Returns:
            dict: 克隆执行计划
        """
        model = next(
            (m for m in BusinessCloneEngine.SUCCESS_MODELS if m["id"] == model_id),
            None
        )
        if not model:
            return {"error": f"Model {model_id} not found"}

        if target_market not in model["replicable_to"]:
            return {"error": f"{target_market} not in replicable markets for {model_id}"}

        adaptation = model.get("adaptation_needed", {}).get(target_market, "")

        return {
            "source_model": model["id"],
            "source_market": model["source_market"],
            "target_market": target_market,
            "product": model["product"],
            "estimated_conversion": round(model["conversion_rate"] * 0.85, 1),
            "estimated_aov": BusinessCloneEngine._estimate_aov(
                model["avg_order_value"], target_market
            ),
            "execution_plan": {
                "phase_1_setup": ["register_domain", "setup_whatsapp", "create_listings"],
                "phase_2_content": ["translate_materials", "localize_culture", "create_ads"],
                "phase_3_launch": ["test_ads", "monitor_ctr", "optimize"],
                "phase_4_scale": ["scale_budget", "expand_channels"],
            },
            "adaptation_required": adaptation if adaptation else "None",
            "estimated_time_to_revenue_days": 45,
            "initial_investment": BusinessCloneEngine._estimate_investment(target_market),
        }

    @staticmethod
    def _estimate_investment(market: str) -> dict:
        """估算初始投资"""
        base = {"US": 3000, "AE": 2500, "GB": 2000, "AU": 2000, "SA": 2500}
        total = base.get(market, 1500)
        return {
            "total": total,
            "breakdown": {
                "website_domain": 200,
                "ads_test_budget": int(total * 0.5),
                "content_creation": int(total * 0.25),
                "misc": int(total * 0.05),
            },
        }

    @staticmethod
    def get_all_models() -> list:
        """获取所有成功模型"""
        return [
            {
                "id": m["id"],
                "source_market": m["source_market"],
                "industry": m["source_industry"],
                "product": m["product"],
                "conversion_rate": m["conversion_rate"],
                "avg_order_value": m["avg_order_value"],
                "replicable_markets": m["replicable_to"],
            }
            for m in BusinessCloneEngine.SUCCESS_MODELS
        ]


# 快捷入口
clone = BusinessCloneEngine()


def find_opportunities(source_market: str = "") -> list:
    return BusinessCloneEngine.find_clone_opportunities(source_market)


def create_plan(model_id: str, target_market: str) -> dict:
    return BusinessCloneEngine.create_clone_plan(model_id, target_market)
