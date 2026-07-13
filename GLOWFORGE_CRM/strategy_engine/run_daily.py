"""Run Daily — V3 CRON 入口

每日执行完整策略分析、学习循环、广告收入闭环、自增长系统。
运行方式:
    python -m strategy_engine.run_daily                          # V3.0 dry-run
    python -m strategy_engine.run_daily --with-ads               # V3.0 + V3.1
    python -m strategy_engine.run_daily --with-growth            # V3.0+V3.1+V3.2
    python -m strategy_engine.run_daily --no-dry-run              # 实际写入
    python -m strategy_engine.run_daily --with-ads --no-dry-run    # V3.0+V3.1 上线
    python -m strategy_engine.run_daily --with-growth --no-dry-run # 全部上线
"""
import argparse
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("strategy_engine.run_daily")


def main():
    parser = argparse.ArgumentParser(description="V3.x Strategy Engine Daily Run")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="预览模式（默认启用）")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="执行实际写入")
    parser.add_argument("--with-ads", action="store_true",
                        help="同时运行 V3.1 Ad Revenue Closed Loop")
    parser.add_argument("--with-growth", action="store_true",
                        help="同时运行 V3.2 Self-Optimizing Growth System")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    # --with-growth 隐含 --with-ads
    if args.with_growth:
        args.with_ads = True

    version_label = "3.2" if args.with_growth else ("3.1" if args.with_ads else "3.0")

    logger.info("=" * 50)
    logger.info(f"V{version_label} Strategy Engine — Daily Run")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Date: {datetime.now().isoformat()}")
    logger.info("=" * 50)

    # 1. 完整策略分析
    logger.info("[1/3] Running strategy analysis...")
    from strategy_engine.core.strategy_engine import StrategyEngine
    report = StrategyEngine.run_full_analysis(dry_run=dry_run)
    logger.info(f"  Markets scored: {report['market_strategy'].get('total_markets', 0)}")
    logger.info(f"  Products scored: {report['product_strategy'].get('total_products', 0)}")
    logger.info(f"  Pricing strategies: {len(report['pricing_strategy'].get('strategies', []))}")
    logger.info(f"  Policy compliant: {report['policy_result'].get('all_approved', False)}")

    # 2. 决策路由
    logger.info("[2/3] Routing decisions to V2...")
    from strategy_engine.core.decision_router import DecisionRouter
    directives = DecisionRouter.route_strategy(report)
    logger.info(f"  Market directives: {len(directives['market_directives'])}")
    logger.info(f"  Product directives: {len(directives['product_directives'])}")
    logger.info(f"  Pricing directives: {len(directives['pricing_directives'])}")
    logger.info(f"  Policy warnings: {len(directives['policy_warnings'])}")

    # 3. 学习循环
    logger.info("[3/3] Running learning cycle...")
    from strategy_engine.learning.feedback_loop import FeedbackLoop
    learning = FeedbackLoop.run_learning_cycle(dry_run=dry_run)
    logger.info(f"  V2 insights: {'available' if learning.get('v2_insights') else 'unavailable'}")
    logger.info(f"  Effectiveness score: {learning.get('strategy_effectiveness', {}).get('effectiveness_score', 'N/A')}")
    logger.info(f"  Learned adjustments: {len(learning.get('learned_adjustments', []))}")

    result = {
        "run_date": datetime.now().isoformat(),
        "dry_run": dry_run,
        "strategy_report": report,
        "directives": directives,
        "learning": learning,
    }

    # 4. （可选）广告收入闭环 V3.1
    if args.with_ads:
        result["ads"] = _run_ad_closed_loop(dry_run)

    # 5. （可选）自增长系统 V3.2
    if args.with_growth:
        result["growth"] = _run_growth_system(report, result.get("ads"), dry_run)

    if not dry_run:
        result["_saved"] = True
        _save_run_record(result)

    ver = "3.2" if args.with_growth else ("3.1" if args.with_ads else "3.0")
    logger.info("=" * 50)
    logger.info(f"V{ver} Daily Run Complete")
    logger.info(f"Mode: {'DRY RUN (no data written)' if dry_run else 'LIVE'}")
    logger.info("=" * 50)

    return result


def _run_ad_closed_loop(dry_run):
    """V3.1 Ad Revenue Closed Loop"""
    logger.info("[4/4] Running Ad Revenue Closed Loop...")

    try:
        from strategy_engine.ads.revenue_attribution import RevenueAttribution
        from strategy_engine.ads.roi_engine import ROIEngine
        from strategy_engine.ads.budget_allocator import BudgetAllocator

        # 4a. 收入归因
        attribution = RevenueAttribution.attribute_revenue(days=90)
        logger.info(f"  Attributed: {attribution['summary'].get('total_attributed_revenue', 0)} revenue"
                    f" from {attribution['summary'].get('attributed_sources', 0)} sources")

        # 4b. ROI 计算
        roi = ROIEngine.calculate_roi(attribution_data=attribution)
        logger.info(f"  Overall ROI: {roi['summary'].get('overall_roi', 0)}x"
                    f" | Sources: {roi['summary'].get('sources_analyzed', 0)}"
                    f" | Campaigns: {roi['summary'].get('campaigns_analyzed', 0)}")

        # 4c. 预算分配
        budget = BudgetAllocator.allocate_budget(roi_data=roi)
        logger.info(f"  Decisions: ↑{budget['summary'].get('increase_budget', 0)}"
                    f" →{budget['summary'].get('maintain', 0)}"
                    f" ⏸{budget['summary'].get('pause', 0)}")

        return {
            "attribution": attribution,
            "roi": roi,
            "budget": budget,
        }

    except Exception as e:
        logger.warning(f"Ad closed loop failed: {e}")
        return {"error": str(e)}


def _run_growth_system(strategy_report, ads_data, dry_run):
    """V3.2 Self-Optimizing Growth System"""
    logger.info("[5/5] Running Self-Optimizing Growth System...")

    try:
        from strategy_engine.growth.self_learning_loop import SelfLearningLoop

        roi_data = None
        if ads_data and "roi" in ads_data:
            roi_data = ads_data["roi"]

        # 运行完整自进化循环
        growth = SelfLearningLoop.run_growth_cycle(
            strategy_report=strategy_report,
            roi_data=roi_data,
            dry_run=dry_run,
        )

        # 日志输出
        ev = growth["evaluation"]
        logger.info(f"  Cycle #{growth['cycle_number']} | "
                    f"Evaluated: {ev['total_evaluated']}"
                    f" | ↑{ev['improved']} ↓{ev['declined']}")

        new_exp = growth["new_experiments"]["summary"]
        logger.info(f"  New experiments: {new_exp['experiments_generated']}"
                    f" (top score: {new_exp.get('top_score', 0)})")

        pruned = growth["pruned"]
        if pruned["removed"] > 0:
            logger.info(f"  Pruned: {pruned['removed']} stale strategies")

        expansion = growth["expansion_signals"]
        if expansion:
            logger.info(f"  Expansion signals: {len(expansion)} markets")

        bandit = growth["bandit_update"]
        logger.info(f"  Bandit: {bandit['total_strategies']} strategies"
                    f" | best: {bandit.get('top_strategy', 'N/A')}"
                    f" @ {bandit.get('top_weight', 0):.2f}")

        return growth

    except Exception as e:
        logger.warning(f"Growth system failed: {e}")
        return {"error": str(e)}


def _save_run_record(result):
    """将运行记录写入 strategy_state.json"""
    state_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "strategy_state.json",
    )

    try:
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        else:
            state = {"version": "3.0.0", "runs": []}

        state["latest_run"] = result["run_date"]
        state["runs"].append({
            "date": result["run_date"],
            "markets": len(result["strategy_report"]["market_strategy"].get("scored_markets", [])),
            "products": len(result["strategy_report"]["product_strategy"].get("scored_products", [])),
            "policy_approved": result["strategy_report"]["policy_result"].get("all_approved", False),
        })

        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, state_path)
    except Exception as e:
        logger.warning(f"Failed to save run record: {e}")


if __name__ == "__main__":
    main()
