"""Budget Allocator — 预算分配系统

基于 ROI 数据自动决定：
- 哪个广告继续投
- 哪个广告加预算
- 哪个广告暂停
- 预算如何重新分配

核心规则:
  ROI < 1   → pause
  ROI 1-3   → maintain
  ROI > 3   → increase_budget
"""
import logging
from datetime import datetime

logger = logging.getLogger("budget_allocator")

# 决策阈值
ROI_PAUSE = 1.0
ROI_MAINTAIN = 3.0

# 预算调整幅度
BUDGET_INCREASE_PCT = 0.30
BUDGET_REDUCE_PCT = 0.50


class BudgetAllocator:
    """预算分配引擎"""

    @staticmethod
    def allocate_budget(roi_data=None):
        """基于 ROI 数据生成预算分配方案

        参数:
            roi_data: ROIEngine.calculate_roi() 的输出，或 None（自动获取）

        返回:
            dict: {
                decisions: [{ source, roi, action, reason }],
                budget_plan: { source: { recommended_budget, change_pct } },
                summary: { total_budget, sources_increase, sources_pause, ... }
            }
        """
        if roi_data is None:
            from strategy_engine.ads.roi_engine import ROIEngine
            roi_data = ROIEngine.calculate_roi()

        decisions = []
        total_profit = roi_data.get("summary", {}).get("total_profit", 0)
        total_revenue = roi_data.get("summary", {}).get("total_revenue", 0)

        for src, data in roi_data.get("by_source", {}).items():
            roi = data.get("roi", 0)
            profit = data.get("profit", 0)
            action, reason = BudgetAllocator._decide_action(roi, profit)

            decisions.append({
                "source": src,
                "roi": roi,
                "profit": profit,
                "revenue": data.get("revenue", 0),
                "cost": data.get("estimated_ad_cost", 0),
                "orders": data.get("orders", 0),
                "action": action,
                "reason": reason,
            })

        # 生成预算方案
        budget_plan = BudgetAllocator._build_budget_plan(decisions, total_profit)

        # 汇总
        increases = sum(1 for d in decisions if d["action"] == "increase_budget")
        maintains = sum(1 for d in decisions if d["action"] == "maintain")
        pauses = sum(1 for d in decisions if d["action"] == "pause")

        return {
            "decisions": decisions,
            "budget_plan": budget_plan,
            "summary": {
                "total_decisions": len(decisions),
                "increase_budget": increases,
                "maintain": maintains,
                "pause": pauses,
                "total_revenue": round(total_revenue, 2),
                "total_profit": round(total_profit, 2),
            },
        }

    @staticmethod
    def _decide_action(roi, profit):
        """单条决策逻辑"""
        if roi < ROI_PAUSE:
            return "pause", f"ROI {roi:.2f} < {ROI_PAUSE:.0f}，建议暂停投放"
        elif roi >= ROI_MAINTAIN:
            return "increase_budget", (
                f"ROI {roi:.2f} >= {ROI_MAINTAIN:.0f}，建议增加预算 "
                f"{BUDGET_INCREASE_PCT:.0%}"
            )
        else:
            return "maintain", f"ROI {roi:.2f} 在合理范围，建议维持现有预算"

    @staticmethod
    def _build_budget_plan(decisions, total_profit):
        """基于决策生成预算分配方案"""
        plan = {}

        # 先找出所有可再投资的利润
        investable = total_profit * 0.5  # 最多 50% 利润再投资
        total_cost = sum(d["cost"] for d in decisions if d["cost"] > 0)

        for d in decisions:
            if d["action"] == "increase_budget":
                increase_amount = round(d["cost"] * BUDGET_INCREASE_PCT, 2)
                plan[d["source"]] = {
                    "action": "increase",
                    "current_cost": round(d["cost"], 2),
                    "recommended_additional": increase_amount,
                    "change_pct": BUDGET_INCREASE_PCT,
                    "new_total": round(d["cost"] + increase_amount, 2),
                }
            elif d["action"] == "maintain":
                plan[d["source"]] = {
                    "action": "maintain",
                    "current_cost": round(d["cost"], 2),
                    "recommended_additional": 0,
                    "change_pct": 0,
                    "new_total": round(d["cost"], 2),
                }
            else:  # pause
                plan[d["source"]] = {
                    "action": "pause",
                    "current_cost": round(d["cost"], 2),
                    "recommended_additional": -round(d["cost"], 2),
                    "change_pct": -1.0,
                    "new_total": 0,
                    "redirect_to": BudgetAllocator._suggest_redirect(
                        decisions, d["source"]
                    ),
                }

        return plan

    @staticmethod
    def _suggest_redirect(decisions, paused_source):
        """建议暂停渠道的预算重定向目标"""
        best = None
        for d in decisions:
            if d["action"] == "increase_budget":
                if best is None or d["roi"] > best["roi"]:
                    best = d
        if best:
            return f"建议将预算转移至 {best['source']}（ROI {best['roi']:.2f}）"
        return "暂无更优投放渠道"

    @staticmethod
    def get_budget_plan(dry_run=True):
        """一键获取完整预算方案"""
        from strategy_engine.ads.roi_engine import ROIEngine

        roi_data = ROIEngine.calculate_roi()
        result = BudgetAllocator.allocate_budget(roi_data=roi_data)

        result["_dry_run"] = dry_run
        result["generated_at"] = datetime.now().isoformat()

        if not dry_run:
            pass  # 预留：写入 ad_strategy.json / budget_plan.json

        return result

    @staticmethod
    def analyze_budget_shift(decisions):
        """计算预算转移总量"""
        paused_budget = sum(
            d.get("cost", 0) for d in decisions if d["action"] == "pause"
        )
        increase_budget = sum(
            d.get("cost", 0) * BUDGET_INCREASE_PCT
            for d in decisions if d["action"] == "increase_budget"
        )

        return {
            "freed_from_paused": round(paused_budget, 2),
            "needed_for_increase": round(increase_budget, 2),
            "surplus": round(paused_budget - increase_budget, 2),
            "note": "暂停渠道释放的预算可覆盖增长需求"
            if paused_budget >= increase_budget
            else "增长需求超过释放预算，需额外注入资金",
        }
