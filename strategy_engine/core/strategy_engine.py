"""Strategy Engine — V3 主编排器

串联 Market + Product + Pricing 三大分析引擎，
经过 Policy 过滤后生成最终策略报告。
"""
import logging
from datetime import datetime

logger = logging.getLogger("strategy_engine")


class StrategyEngine:
    """主编排器 — 执行完整策略分析"""

    @staticmethod
    def run_full_analysis(dry_run=True):
        """执行完整策略分析

        流程:
          1. 收集 Metrics
          2. 并行分析市场/产品/定价
          3. 产品×市场匹配矩阵
          4. Policy 合规检查
          5. 生成最终策略报告

        返回:
            dict: {
                analysis_date, market_strategy, product_strategy,
                pricing_strategy, policy_result, demand_fit_matrix,
                metrics, recommendations, dry_run
            }
        """
        analysis_date = datetime.now().isoformat()

        # 1. 收集指标
        metrics = StrategyEngine._collect_metrics()

        # 2. 并行分析
        market_strategy = StrategyEngine._analyze_market(dry_run)
        product_strategy = StrategyEngine._analyze_product(dry_run)
        pricing_strategy = StrategyEngine._analyze_pricing(dry_run)
        demand_fit = StrategyEngine._analyze_demand_fit()

        # 3. 整合策略报告
        strategy_report = {
            "analysis_date": analysis_date,
            "market_strategy": market_strategy,
            "product_strategy": product_strategy,
            "pricing_strategy": pricing_strategy,
            "demand_fit_matrix": demand_fit,
            "metrics": metrics,
        }

        # 4. Policy 合规检查
        policy_result = StrategyEngine._check_policy(strategy_report)

        # 5. 生成建议
        recommendations = StrategyEngine._generate_recommendations(
            market_strategy, product_strategy, pricing_strategy, policy_result
        )

        return {
            "analysis_date": analysis_date,
            "market_strategy": market_strategy,
            "product_strategy": product_strategy,
            "pricing_strategy": pricing_strategy,
            "demand_fit_matrix": demand_fit,
            "policy_result": policy_result,
            "metrics": metrics,
            "recommendations": recommendations,
            "dry_run": dry_run,
        }

    @staticmethod
    def _collect_metrics():
        try:
            from strategy_engine.learning.metrics_collector import MetricsCollector
            return MetricsCollector.collect_all()
        except Exception as e:
            logger.warning(f"Metrics collection failed: {e}")
            return {}

    @staticmethod
    def _analyze_market(dry_run):
        try:
            from strategy_engine.market.market_scoring import MarketScoring
            scored = MarketScoring.score_markets(dry_run=dry_run)
            return {
                "scored_markets": scored,
                "top_markets": scored[:3] if scored else [],
                "total_markets": len(scored),
            }
        except Exception as e:
            logger.warning(f"Market analysis failed: {e}")
            return {"scored_markets": [], "top_markets": [], "total_markets": 0}

    @staticmethod
    def _analyze_product(dry_run):
        try:
            from strategy_engine.product.product_scoring import ProductScoring
            scored = ProductScoring.score_products(dry_run=dry_run)
            return {
                "scored_products": scored,
                "top_products": scored[:3] if scored else [],
                "total_products": len(scored),
            }
        except Exception as e:
            logger.warning(f"Product analysis failed: {e}")
            return {"scored_products": [], "top_products": [], "total_products": 0}

    @staticmethod
    def _analyze_pricing(dry_run):
        try:
            from strategy_engine.pricing.pricing_strategy import PricingStrategy
            strategy = PricingStrategy.develop_strategy(dry_run=dry_run)
            return strategy
        except Exception as e:
            logger.warning(f"Pricing analysis failed: {e}")
            return {"strategies": [], "overall": {}}

    @staticmethod
    def _analyze_demand_fit():
        try:
            from strategy_engine.product.demand_fit import DemandFit
            return {
                "matrix": DemandFit.analyze_product_market_fit(),
                "recommended_combinations": DemandFit.get_recommended_combinations(),
            }
        except Exception as e:
            logger.warning(f"Demand fit analysis failed: {e}")
            return {"matrix": [], "recommended_combinations": []}

    @staticmethod
    def _check_policy(report):
        try:
            from strategy_engine.policy.constraint_engine import ConstraintEngine
            return ConstraintEngine.check_constraints(report)
        except Exception as e:
            logger.warning(f"Policy check failed: {e}")
            return {"all_approved": False, "blocked_actions": [], "error": str(e)}

    @staticmethod
    def _generate_recommendations(market, product, pricing, policy):
        recs = []

        top_markets = market.get("top_markets", [])
        if top_markets:
            names = [m["country_code"] for m in top_markets]
            recs.append(f"重点市场: {', '.join(names)}")

        top_products = product.get("top_products", [])
        if top_products:
            names = [p["product_name"] for p in top_products]
            recs.append(f"核心产品: {', '.join(names)}")

        policy_result = policy or {}
        if not policy_result.get("all_approved", True):
            recs.append("策略存在合规问题，请查看 Policy 违例详情")

        return recs
