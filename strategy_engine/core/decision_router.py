"""Decision Router — V3策略→V2执行指令

将 V3 的策略决策转换为 V2 可执行的指令，
包括市场聚焦、产品推荐、定价调整等。
"""
import logging
from datetime import datetime

logger = logging.getLogger("decision_router")


class DecisionRouter:
    """V3→V2 决策路由桥接"""

    @staticmethod
    def route_strategy(strategy_report):
        """将 V3 策略报告转换为 V2 执行指令

        返回:
            dict: {
                route_date, routing_version,
                market_directives, product_directives,
                pricing_directives, policy_warnings
            }
        """
        directives = {
            "route_date": datetime.now().isoformat(),
            "routing_version": "3.0.0",
            "market_directives": [],
            "product_directives": [],
            "pricing_directives": [],
            "policy_warnings": [],
        }

        # 市场指令 — 告诉 V2 聚焦哪些市场
        market = strategy_report.get("market_strategy", {})
        for m in market.get("top_markets", []):
            directives["market_directives"].append({
                "action": "focus_market",
                "target": m["country_code"],
                "params": {
                    "v3_score": m.get("v3_score"),
                    "recommendation": m.get("recommendation"),
                },
            })

        # 产品指令 — 告诉 V2 推荐哪些产品
        product = strategy_report.get("product_strategy", {})
        for p in product.get("top_products", []):
            directives["product_directives"].append({
                "action": "recommend_product",
                "target": p["product_name"],
                "params": {
                    "product_score": p.get("product_score"),
                    "recommendation": p.get("recommendation"),
                },
            })

        # 定价指令 — 告诉 V2 各市场/产品的目标价格
        pricing = strategy_report.get("pricing_strategy", {})
        for s in pricing.get("strategies", [])[:5]:
            directives["pricing_directives"].append({
                "action": "set_pricing",
                "target": f"{s['country']}:{s['product']}",
                "params": {
                    "target_margin": s.get("target_margin"),
                    "market_price": s.get("market_price"),
                    "price_factor": s.get("price_factor"),
                },
            })

        # 政策警告 — 通知 V2 被阻止的行动
        policy = strategy_report.get("policy_result", {})
        if not policy.get("all_approved", True):
            for b in policy.get("blocked_actions", []):
                directives["policy_warnings"].append(
                    f"[{b.get('blocking_policy', '?')}] {b.get('reason', '')}"
                )

        return directives
