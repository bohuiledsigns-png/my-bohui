"""Ad Optimizer — 自动广告优化系统

AI自动做A/B测试：
  视频A vs 视频B vs 视频C
  价格A vs B vs C
  标题A vs B vs C

系统自动选择：CTR最高 + ROI最高组合
"""

import sys
import os
import random
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class AdOptimizer:
    """广告自动优化系统 — AI自动A/B测试"""

    # 测试变量
    TEST_VARIABLES = {
        "headline": {
            "name": "Headline",
            "variants_count": 3,
            "test_duration_hours": 48,
            "success_metric": "ctr",
        },
        "image": {
            "name": "Image/Creative",
            "variants_count": 3,
            "test_duration_hours": 72,
            "success_metric": "ctr",
        },
        "cta": {
            "name": "Call to Action",
            "variants_count": 2,
            "test_duration_hours": 24,
            "success_metric": "conversion_rate",
        },
        "audience": {
            "name": "Audience Targeting",
            "variants_count": 3,
            "test_duration_hours": 96,
            "success_metric": "cpa",
        },
        "price": {
            "name": "Price Point",
            "variants_count": 3,
            "test_duration_hours": 72,
            "success_metric": "roi",
        },
        "landing_page": {
            "name": "Landing Page",
            "variants_count": 2,
            "test_duration_hours": 48,
            "success_metric": "conversion_rate",
        },
    }

    @staticmethod
    def create_ab_test(platform: str, variable: str,
                       base_variant: str, variants: list) -> dict:
        """创建A/B测试方案

        Args:
            platform: 平台名称
            variable: 测试变量 (headline/image/cta/audience/price/landing_page)
            base_variant: 基准版本
            variants: 测试版本列表

        Returns:
            dict: {test_id, platform, variable, variants, duration, metrics}
        """
        var_config = AdOptimizer.TEST_VARIABLES.get(variable, {})

        test_variants = [{"id": "control", "content": base_variant, "is_control": True}]
        for i, v in enumerate(variants):
            test_variants.append({
                "id": f"variant_{i+1}",
                "content": v,
                "is_control": False,
            })

        return {
            "test_id": f"ab_{platform}_{variable}_{int(datetime.now().timestamp())}",
            "platform": platform,
            "variable": variable,
            "variable_name": var_config.get("name", variable),
            "variants": test_variants,
            "variants_count": len(test_variants),
            "test_duration_hours": var_config.get("test_duration_hours", 48),
            "min_confidence": 0.95,
            "success_metric": var_config.get("success_metric", "ctr"),
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "estimated_end": (datetime.now() + timedelta(
                hours=var_config.get("test_duration_hours", 48)
            )).isoformat(),
        }

    @staticmethod
    def simulate_results(test: dict) -> dict:
        """模拟测试结果（实际应用中从广告平台获取）

        Args:
            test: A/B测试方案

        Returns:
            dict: 带结果的测试
        """
        variants = test.get("variants", [])
        results = []

        for v in variants:
            # 模拟数据
            impressions = random.randint(1000, 5000)
            clicks = int(impressions * random.uniform(0.02, 0.08))
            conversions = int(clicks * random.uniform(0.05, 0.20))
            spend = round(random.uniform(50, 200), 2)

            results.append({
                "variant_id": v["id"],
                "is_control": v.get("is_control", False),
                "content": v["content"],
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "spend": spend,
                "ctr": round(clicks / impressions * 100, 2),
                "conversion_rate": round(conversions / clicks * 100, 2) if clicks > 0 else 0,
                "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
                "roi": round(((conversions * 300) - spend) / spend * 100, 1) if spend > 0 else 0,
            })

        # 找出优胜者
        metric = test.get("success_metric", "ctr")
        winner = max(results, key=lambda r: r.get(metric, 0))

        test["results"] = results
        test["winner"] = {
            "variant_id": winner["variant_id"],
            "content": winner["content"],
            "winning_metric": metric,
            "winning_value": winner.get(metric, 0),
            "improvement_pct": AdOptimizer._calculate_improvement(results, metric),
        }
        test["status"] = "completed"

        return test

    @staticmethod
    def _calculate_improvement(results: list, metric: str) -> float:
        """计算优胜者相比基准的提升百分比"""
        control = next((r for r in results if r.get("is_control")), None)
        winner_val = max(r.get(metric, 0) for r in results)
        control_val = control.get(metric, 0) if control else 0

        if control_val > 0:
            return round((winner_val - control_val) / control_val * 100, 1)
        return 0

    @staticmethod
    def optimize_campaign(product: str, target: str, country: str) -> dict:
        """为营销活动生成完整优化方案

        Args:
            product: 产品
            target: 目标客户
            country: 国家

        Returns:
            dict: {ab_tests, optimization_plan, estimated_improvement}
        """
        # 生成多变量A/B测试
        tests = []
        for variable in ["headline", "image", "cta", "audience", "price"]:
            # 生成变体
            if variable == "headline":
                variants = [
                    f"Premium {product} for {target}",
                    f"Transform Your {target} Business",
                    f"Stand Out with Custom {product}",
                ]
            elif variable == "image":
                variants = [
                    "Product hero shot",
                    "Installation in progress",
                    "Before/after comparison",
                ]
            elif variable == "cta":
                variants = ["Get Free Quote", "Contact Us Today"]
            elif variable == "price":
                variants = ["Standard pricing", "Premium pricing", "Budget option"]
            else:
                variants = ["Broad targeting", "Lookalike audience", "Retargeting"]

            test = AdOptimizer.create_ab_test(
                f"{country}_{product}", variable,
                variants[0], variants[1:]
            )
            tests.append(test)

        return {
            "product": product,
            "target": target,
            "country": country,
            "total_tests": len(tests),
            "estimated_time_hours": sum(
                t["test_duration_hours"] for t in tests
            ),
            "estimated_improvement": "15-30% CTR increase, 20-40% ROI improvement",
            "ab_tests": tests,
        }

    @staticmethod
    def get_optimization_report(results: list) -> dict:
        """生成优化报告"""
        if not results:
            return {}

        total_improvement = sum(
            r.get("winner", {}).get("improvement_pct", 0) for r in results
        )

        return {
            "tests_completed": len(results),
            "average_improvement": round(total_improvement / len(results), 1) if results else 0,
            "best_test": max(results, key=lambda r: r.get("winner", {}).get("improvement_pct", 0)),
            "worst_test": min(results, key=lambda r: r.get("winner", {}).get("improvement_pct", 0)),
            "recommended_next_actions": [
                "Scale winning ad sets to 2x budget",
                "Apply winning headlines to all campaigns",
                "Test winner vs new creative in 7 days",
            ],
        }


# 快捷入口
optimizer = AdOptimizer()


def create_test(platform: str, variable: str, base: str, variants: list) -> dict:
    return AdOptimizer.create_ab_test(platform, variable, base, variants)


def optimize(product: str, target: str, country: str) -> dict:
    return AdOptimizer.optimize_campaign(product, target, country)
