"""Capital Allocator — 资金分配引擎

系统自动决定钱去哪：
  60% → 高增长市场
  20% → 稳定现金流公司
  10% → 新实验项目
  10% → 风险储备

本质：AI做"投资经理 + CEO"
"""

import sys
import os
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class CapitalAllocator:
    """资金分配引擎 — AI投资经理"""

    # 默认分配策略
    DEFAULT_ALLOCATION = {
        "high_growth": {"pct": 60, "label": "High Growth Markets", "risk": "high"},
        "stable_cashflow": {"pct": 20, "label": "Stable Cash Flow", "risk": "low"},
        "new_experiments": {"pct": 10, "label": "New Experiments", "risk": "very_high"},
        "reserve": {"pct": 10, "label": "Risk Reserve", "risk": "none"},
    }

    @staticmethod
    def allocate(total_capital: float, portfolio: list = None) -> dict:
        """分配资金到各业务线

        Args:
            total_capital: 总可用资金
            portfolio: 现有投资组合 [{company, market, profit, growth}]

        Returns:
            dict: {allocation, recommendations, expected_roi}
        """
        if portfolio:
            allocation = CapitalAllocator._smart_allocate(total_capital, portfolio)
        else:
            allocation = CapitalAllocator._default_allocate(total_capital)

        return {
            "total_capital": total_capital,
            "allocated_at": datetime.now().isoformat(),
            "allocation": allocation,
            "strategy_summary": CapitalAllocator._generate_strategy(allocation),
            "expected_monthly_roi": CapitalAllocator._estimate_roi(allocation),
        }

    @staticmethod
    def _default_allocate(total_capital: float) -> list:
        """默认分配策略"""
        result = []
        for key, config in CapitalAllocator.DEFAULT_ALLOCATION.items():
            amount = round(total_capital * config["pct"] / 100, 2)
            result.append({
                "category": key,
                "label": config["label"],
                "amount": amount,
                "pct": config["pct"],
                "risk": config["risk"],
            })
        return result

    @staticmethod
    def _smart_allocate(total_capital: float, portfolio: list) -> list:
        """基于投资组合的智能分配"""
        # 计算各业务得分
        scored = []
        for p in portfolio:
            profit = p.get("profit", 0) or p.get("revenue", 0) * 0.2
            growth = p.get("growth", 0) or 5
            score = profit * 0.6 + growth * 0.4
            scored.append({**p, "_score": score})

        scored.sort(key=lambda x: x["_score"], reverse=True)

        # 分配：高分业务获更多资金
        result = []
        high_growth_amount = total_capital * 0.6
        if scored:
            top_count = min(len(scored), 3)
            for i in range(top_count):
                weight = (top_count - i) / sum(range(1, top_count + 1))
                amount = round(high_growth_amount * weight, 2)
                result.append({
                    "category": "high_growth",
                    "label": f"{scored[i].get('company', 'Business')} ({scored[i].get('market', '')})",
                    "amount": amount,
                    "pct": round(amount / total_capital * 100, 1),
                    "risk": "medium",
                    "expected_growth": f"+{scored[i].get('growth', 10)}%",
                })

        # 剩余默认分配
        remaining = total_capital - sum(r["amount"] for r in result)
        if remaining > 0:
            for key, config in CapitalAllocator.DEFAULT_ALLOCATION.items():
                if key == "high_growth":
                    continue
                amount = round(remaining * config["pct"] / 40, 2)  # 40 = 20+10+10
                result.append({
                    "category": key,
                    "label": config["label"],
                    "amount": amount,
                    "pct": round(amount / total_capital * 100, 1),
                    "risk": config["risk"],
                })

        return result

    @staticmethod
    def _generate_strategy(allocation: list) -> str:
        """生成分配策略描述"""
        high_growth = next((a for a in allocation if a["category"] == "high_growth"), {})
        return (
            f"Primary focus on high-growth opportunities ({high_growth.get('pct', 0)}% of capital), "
            f"with stable cash flow businesses providing foundation "
            f"and experimental projects driving future growth."
        )

    @staticmethod
    def _estimate_roi(allocation: list) -> dict:
        """估算预期ROI"""
        roi_by_risk = {"high": 0.25, "medium": 0.15, "low": 0.08, "very_high": 0.40, "none": 0.02}
        weighted_roi = 0
        total = 0

        for a in allocation:
            risk = a.get("risk", "medium")
            roi = roi_by_risk.get(risk, 0.1)
            weighted_roi += a["amount"] * roi
            total += a["amount"]

        avg_roi = round(weighted_roi / total * 100, 1) if total > 0 else 0
        return {
            "monthly_roi_pct": avg_roi,
            "monthly_return": round(total * avg_roi / 100, 2),
            "annualized_roi": round(avg_roi * 12, 1),
        }

    @staticmethod
    def rebalance(current_allocation: list, performance: list) -> dict:
        """根据表现重新平衡投资组合

        Args:
            current_allocation: 当前分配 [{label, amount, category}]
            performance: 表现数据 [{label, roi, growth}]

        Returns:
            dict: {reallocation, changes, reason}
        """
        changes = []
        new_allocation = []

        for curr in current_allocation:
            perf = next(
                (p for p in performance if p.get("label") == curr["label"]),
                None
            )
            if perf:
                roi = perf.get("roi", 0)
                if roi > 20:
                    # 表现好 → 增加投入
                    increase = round(curr["amount"] * 0.15, 2)
                    new_amount = curr["amount"] + increase
                    changes.append(f"+${increase} to {curr['label']} (ROI {roi}%)")
                elif roi < 5:
                    # 表现差 → 减少投入
                    decrease = round(curr["amount"] * 0.2, 2)
                    new_amount = curr["amount"] - decrease
                    changes.append(f"-${decrease} from {curr['label']} (ROI {roi}%)")
                else:
                    new_amount = curr["amount"]
            else:
                new_amount = curr["amount"]

            new_allocation.append({**curr, "amount": new_amount})

        return {
            "reallocation": new_allocation,
            "changes": changes,
            "total_changes": len(changes),
            "reason": "Performance-based rebalancing",
        }


# 快捷入口
allocator = CapitalAllocator()


def allocate(total_capital: float, portfolio: list = None) -> dict:
    return CapitalAllocator.allocate(total_capital, portfolio)


def rebalance(current: list, performance: list) -> dict:
    return CapitalAllocator.rebalance(current, performance)
