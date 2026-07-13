"""Profit Model — 利润预测与盈亏平衡分析

为定价决策提供利润预测和盈亏平衡计算支持。
"""
import logging

logger = logging.getLogger("profit_model")

FIXED_MONTHLY_COSTS = {
    "platform_fee": 2000,
    "labor": 15000,
    "marketing": 5000,
    "overhead": 3000,
    "total": 25000,
}


class ProfitModel:
    """利润预测与盈亏平衡分析引擎"""

    @staticmethod
    def calculate_profit_estimate(unit_price, unit_cost, forecast_units, fixed_costs=None):
        """计算利润预估"""
        if fixed_costs is None:
            fixed_costs = FIXED_MONTHLY_COSTS["total"]

        revenue = unit_price * forecast_units
        variable_cost = unit_cost * forecast_units
        gross_profit = revenue - variable_cost
        net_profit = gross_profit - fixed_costs
        margin_pct = round((unit_price - unit_cost) / unit_price * 100, 2) if unit_price > 0 else 0

        return {
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "forecast_units": forecast_units,
            "revenue": round(revenue, 2),
            "variable_cost": round(variable_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "fixed_costs": fixed_costs,
            "net_profit": round(net_profit, 2),
            "unit_margin_pct": margin_pct,
            "is_profitable": net_profit > 0,
        }

    @staticmethod
    def get_break_even(unit_price, unit_cost, fixed_costs=None):
        """计算盈亏平衡点"""
        if fixed_costs is None:
            fixed_costs = FIXED_MONTHLY_COSTS["total"]

        contribution = unit_price - unit_cost
        if contribution <= 0:
            return {
                "error": "边际贡献 <= 0，无法盈亏平衡",
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "contribution": round(contribution, 2),
            }

        break_even_units = fixed_costs / contribution
        break_even_revenue = break_even_units * unit_price

        return {
            "break_even_units": round(break_even_units),
            "break_even_revenue": round(break_even_revenue, 2),
            "unit_margin": round(contribution, 2),
            "margin_pct": round(contribution / unit_price * 100, 2),
            "fixed_costs": fixed_costs,
        }

    @staticmethod
    def get_projection(base_price, unit_cost, growth_rate=0.1, months=6):
        """多期利润预测"""
        projections = []
        cumulative_profit = 0

        for m in range(1, months + 1):
            units = max(1, round(10 * (1 + growth_rate) ** m))
            revenue = base_price * units
            cost = unit_cost * units
            monthly_profit = revenue - cost - FIXED_MONTHLY_COSTS["total"]
            cumulative_profit += monthly_profit

            projections.append({
                "month": m,
                "forecast_units": units,
                "revenue": round(revenue, 2),
                "cost": round(cost, 2),
                "fixed_costs": FIXED_MONTHLY_COSTS["total"],
                "monthly_profit": round(monthly_profit, 2),
                "cumulative_profit": round(cumulative_profit, 2),
            })

        return projections

    @staticmethod
    def get_margin_waterfall(unit_price, unit_cost):
        """利润瀑布图——从售价到净利润的层层分解"""
        selling_price = unit_price
        cost_of_goods = unit_cost
        gross_margin = selling_price - cost_of_goods

        platform_fee_rate = 0.05
        marketing_rate = 0.10
        overhead_rate = 0.05

        platform_fee = selling_price * platform_fee_rate
        marketing_cost = selling_price * marketing_rate
        overhead = selling_price * overhead_rate
        total_costs = cost_of_goods + platform_fee + marketing_cost + overhead
        net_margin = selling_price - total_costs

        return {
            "selling_price": selling_price,
            "cost_of_goods": round(cost_of_goods, 2),
            "gross_margin": round(gross_margin, 2),
            "gross_margin_pct": round(gross_margin / selling_price * 100, 2),
            "platform_fee": round(platform_fee, 2),
            "marketing_cost": round(marketing_cost, 2),
            "overhead": round(overhead, 2),
            "total_unit_cost": round(total_costs, 2),
            "net_margin": round(net_margin, 2),
            "net_margin_pct": round(net_margin / selling_price * 100, 2),
        }
