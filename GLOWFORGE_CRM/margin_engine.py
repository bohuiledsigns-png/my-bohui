"""Margin Engine — 动态利润引擎（V5）

多币种利润核算、成本结构分析、定价优化建议。
支持按工厂/产品类别/市场区域逐层拆解。
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 默认生产成本（USD，无数据库时回退）
_DEFAULT_PRODUCTION_COST = {
    "led_sign": {"base_cost": 120, "material": 60, "labor": 35, "overhead": 25, "currency": "USD"},
    "neon_sign": {"base_cost": 200, "material": 100, "labor": 65, "overhead": 35, "currency": "USD"},
    "channel_letter": {"base_cost": 80, "material": 40, "labor": 25, "overhead": 15, "currency": "USD"},
    "lightbox": {"base_cost": 150, "material": 75, "labor": 45, "overhead": 30, "currency": "USD"},
    "pylon_sign": {"base_cost": 500, "material": 250, "labor": 150, "overhead": 100, "currency": "USD"},
    "digital_display": {"base_cost": 800, "material": 400, "labor": 250, "overhead": 150, "currency": "USD"},
    "directory_sign": {"base_cost": 100, "material": 50, "labor": 30, "overhead": 20, "currency": "USD"},
    "awning": {"base_cost": 250, "material": 130, "labor": 70, "overhead": 50, "currency": "USD"},
    "floor_sign": {"base_cost": 60, "material": 30, "labor": 18, "overhead": 12, "currency": "USD"},
    "window_sign": {"base_cost": 40, "material": 20, "labor": 12, "overhead": 8, "currency": "USD"},
    "general": {"base_cost": 100, "material": 50, "labor": 30, "overhead": 20, "currency": "USD"},
}

# 默认平台费用比率
_PLATFORM_FEES = {
    "whatsapp": 0.0,
    "aliexpress": 0.08,
    "amazon": 0.15,
    "ebay": 0.12,
    "etsy": 0.05,
    "shopify": 0.02,
    "website": 0.01,
    "direct": 0.0,
    "referral": 0.0,
}

# 默认市场利润目标
_DEFAULT_MARGIN_TARGETS = {
    "NA": {"target": 0.40, "min": 0.25, "competitor_factor": 1.0},
    "EU": {"target": 0.35, "min": 0.20, "competitor_factor": 0.95},
    "APAC": {"target": 0.30, "min": 0.15, "competitor_factor": 0.85},
    "LATAM": {"target": 0.25, "min": 0.12, "competitor_factor": 0.80},
    "MEA": {"target": 0.35, "min": 0.20, "competitor_factor": 0.90},
}


class MarginEngine:
    """动态利润引擎"""

    def calculate_full_cost(self, factory_id: Optional[int] = None,
                            product_category: str = "general",
                            quantity: int = 1) -> dict:
        """计算完整成本

        Args:
            factory_id: 工厂ID（可选）
            product_category: 产品类别
            quantity: 数量

        Returns:
            dict: {
                unit_cost, total_cost,
                material, labor, overhead,
                shipping_estimate, platform_fee,
                currency
            }
        """
        # 基础生产成本
        base = self._get_base_cost(factory_id, product_category)
        unit_cost = base["base_cost"]
        currency = base.get("currency", "USD")

        # 批量折扣
        if quantity >= 100:
            discount = 0.15
        elif quantity >= 50:
            discount = 0.10
        elif quantity >= 20:
            discount = 0.05
        else:
            discount = 0.0

        discounted_unit = round(unit_cost * (1 - discount), 2)
        total_production = round(discounted_unit * quantity, 2)

        return {
            "product_category": product_category,
            "unit_cost": unit_cost,
            "discounted_unit_cost": discounted_unit,
            "quantity": quantity,
            "volume_discount": discount,
            "total_production_cost": total_production,
            "breakdown": {
                "material": round((base.get("material", 0) or 0) * (1 - discount) * quantity, 2),
                "labor": round((base.get("labor", 0) or 0) * (1 - discount) * quantity, 2),
                "overhead": round((base.get("overhead", 0) or 0) * (1 - discount) * quantity, 2),
            },
            "currency": currency,
        }

    def evaluate_margin(self, factory_id: Optional[int],
                        product_category: str,
                        selling_price: float,
                        currency: str = "USD",
                        customer_country: str = "",
                        quantity: int = 1) -> dict:
        """评估一笔交易的利润率

        Args:
            factory_id: 工厂ID
            product_category: 产品类别
            selling_price: 销售价
            currency: 币种
            customer_country: 客户国家
            quantity: 数量

        Returns:
            dict: {revenue, cost, gross_margin, net_margin, ...}
        """
        # 成本
        cost_info = self.calculate_full_cost(factory_id, product_category, quantity)
        total_cost = cost_info["total_production_cost"]
        cost_currency = cost_info["currency"]

        # 销售收入 → 统一转 USD
        try:
            from region_engine import RegionEngine
            re = RegionEngine()
        except Exception:
            re = None

        revenue_usd = selling_price
        if re and currency != "USD":
            revenue_usd = re.convert(selling_price, currency, "USD")["converted_amount"]

        cost_usd = total_cost
        if re and cost_currency != "USD":
            cost_usd = re.convert(total_cost, cost_currency, "USD")["converted_amount"]

        # 平台费用
        platform_fee_rate = _PLATFORM_FEES.get("direct", 0.0)
        platform_fee = round(revenue_usd * platform_fee_rate, 2)

        # 预估运费
        shipping_estimate = 0
        if customer_country:
            try:
                from factory_allocator import FactoryAllocator
                ship = FactoryAllocator().estimate_shipping(customer_country)
                shipping_estimate = ship.get("cost_sea", 0) / 10  # 分摊到单件
            except Exception:
                shipping_estimate = 0

        # 利润计算
        total_cost_with_shipping = cost_usd + shipping_estimate + platform_fee
        gross_margin = revenue_usd - cost_usd
        net_margin = revenue_usd - total_cost_with_shipping
        net_margin_rate = round(net_margin / revenue_usd * 100, 1) if revenue_usd > 0 else 0

        # 市场利润目标
        region_margins = self._get_region_margin_target(customer_country)
        target_margin = region_margins["target"]
        min_margin = region_margins["min"]
        margin_adequate = (net_margin_rate / 100) >= min_margin

        return {
            "revenue": {
                "amount": selling_price,
                "currency": currency,
                "usd_value": revenue_usd,
            },
            "cost": {
                "production": cost_usd,
                "production_currency": cost_currency,
                "shipping_estimate": shipping_estimate,
                "platform_fee": platform_fee,
                "total_cost": round(total_cost_with_shipping, 2),
            },
            "margin": {
                "gross": round(gross_margin, 2),
                "gross_rate": round(gross_margin / revenue_usd * 100, 1) if revenue_usd > 0 else 0,
                "net": round(net_margin, 2),
                "net_rate": net_margin_rate,
            },
            "target": {
                "target_margin_rate": target_margin,
                "min_margin_rate": min_margin,
                "margin_adequate": margin_adequate,
            },
            "details": {
                "factory_id": factory_id,
                "product_category": product_category,
                "quantity": quantity,
                "customer_country": customer_country,
            },
        }

    def optimize_price(self, factory_id: Optional[int],
                       product_category: str,
                       customer_country: str,
                       target_margin: Optional[float] = None,
                       quantity: int = 1) -> dict:
        """计算最优定价

        Args:
            factory_id: 工厂ID
            product_category: 产品类别
            customer_country: 客户国家
            target_margin: 目标利润率（覆盖默认）
            quantity: 数量

        Returns:
            dict: {suggested_price, margin, breakdown, ...}
        """
        cost_info = self.calculate_full_cost(factory_id, product_category, quantity)
        base_cost = cost_info["discounted_unit_cost"]

        # 区域定价系数
        try:
            from region_engine import RegionEngine
            re = RegionEngine()
            region_info = re.get_region_for_country(customer_country)
            markup = region_info.get("default_markup", 1.3)
            base_currency = region_info.get("base_currency", "USD")
        except Exception:
            markup = 1.3
            base_currency = "USD"

        # 市场利润目标
        region_margins = self._get_region_margin_target(customer_country)
        target = target_margin or region_margins["target"]

        # 最低价（保本）
        breakeven = base_cost
        # 目标价
        target_price = round(base_cost / (1 - target), 2)
        # 建议价（含市场溢价）
        suggested_price = round(target_price * markup, 2)
        # 高端价
        premium_price = round(suggested_price * 1.25, 2)

        # 目标利润率下的定价验证
        margin_at_suggested = round(
            (suggested_price - base_cost) / suggested_price * 100, 1
        )

        # 转换为本地币种
        try:
            from region_engine import RegionEngine
            re = RegionEngine()
            local_price = re.convert(suggested_price, "USD", base_currency)["converted_amount"]
        except Exception:
            local_price = suggested_price

        return {
            "product_category": product_category,
            "quantity": quantity,
            "customer_country": customer_country,
            "base_cost": base_cost,
            "price_tiers": {
                "breakeven": round(breakeven, 2),
                "target_price": target_price,
                "suggested_price": suggested_price,
                "premium_price": premium_price,
            },
            "margin_at_suggested": margin_at_suggested,
            "target_margin_rate": target * 100,
            "markup_applied": markup,
            "local_currency_price": {
                "currency": base_currency,
                "amount": local_price,
            },
            "currency": "USD",
        }

    def get_profit_summary(self, region_code: Optional[str] = None,
                           days: int = 30) -> dict:
        """利润汇总

        Args:
            region_code: 区域代码（可选）
            days: 时间范围

        Returns:
            dict: {total_revenue, total_cost, total_profit, profit_rate, ...}
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            query = """SELECT COALESCE(SUM(total_amount), 0) as revenue,
                              COALESCE(SUM(production_cost), 0) as prod_cost,
                              COALESCE(SUM(shipping_cost), 0) as ship_cost,
                              COALESCE(SUM(platform_fee), 0) as plat_fee,
                              COALESCE(SUM(net_profit), 0) as profit,
                              COUNT(*) as orders
                       FROM orders
                       WHERE created_at >= datetime('now', ? || ' days')
                         AND status NOT IN ('cancelled', 'lost')"""
            params = [f"-{days}"]

            if region_code:
                query += " AND region_id = (SELECT id FROM regions WHERE code=?)"
                params.append(region_code)

            row = conn.execute(query, params).fetchone()
            conn.close()

            revenue = float(row["revenue"])
            total_cost = float(row["prod_cost"]) + float(row["ship_cost"]) + float(row["plat_fee"])
            profit = float(row["profit"])
            profit_rate = round(profit / revenue * 100, 1) if revenue > 0 else 0

            return {
                "total_revenue": revenue,
                "production_cost": float(row["prod_cost"]),
                "shipping_cost": float(row["ship_cost"]),
                "platform_fee": float(row["plat_fee"]),
                "total_cost": round(total_cost, 2),
                "net_profit": profit,
                "profit_rate": profit_rate,
                "order_count": row["orders"],
                "period_days": days,
                "region": region_code or "all",
            }
        except Exception:
            return {
                "total_revenue": 0, "total_cost": 0, "net_profit": 0,
                "profit_rate": 0, "order_count": 0, "period_days": days,
                "region": region_code or "all",
            }

    def _get_base_cost(self, factory_id: Optional[int],
                       product_category: str) -> dict:
        """获取基础成本（优先数据库，回退默认）"""
        cat = product_category.lower().strip()

        # 从数据库查
        if factory_id:
            try:
                sys.path.insert(0, BASE_DIR)
                from database import get_db

                conn = get_db()
                row = conn.execute(
                    """SELECT base_cost, material_cost, labor_cost, overhead_cost, currency
                       FROM production_costs
                       WHERE factory_id=? AND product_category=?
                       ORDER BY effective_from DESC LIMIT 1""",
                    (factory_id, cat),
                ).fetchone()
                conn.close()
                if row:
                    return {
                        "base_cost": row["base_cost"],
                        "material": row["material_cost"] or 0,
                        "labor": row["labor_cost"] or 0,
                        "overhead": row["overhead_cost"] or 0,
                        "currency": row["currency"] or "USD",
                    }
            except Exception:
                pass

        # 回退默认
        default = _DEFAULT_PRODUCTION_COST.get(cat) or _DEFAULT_PRODUCTION_COST["general"]
        return {
            "base_cost": default["base_cost"],
            "material": default["material"],
            "labor": default["labor"],
            "overhead": default["overhead"],
            "currency": default["currency"],
        }

    def _get_region_margin_target(self, country_code: str) -> dict:
        """获取区域利润目标"""
        try:
            from region_engine import RegionEngine
            region_info = RegionEngine().get_region_for_country(country_code)
            region_code = region_info["code"]
        except Exception:
            region_code = "APAC"

        return _DEFAULT_MARGIN_TARGETS.get(region_code, {"target": 0.30, "min": 0.15, "competitor_factor": 0.85})


# ==================== 测试 ====================
if __name__ == "__main__":
    me = MarginEngine()

    print("=== Full Cost (led_sign) ===")
    cost = me.calculate_full_cost(None, "led_sign", 1)
    print(f"  Unit: {cost['unit_cost']} {cost['currency']}")
    print(f"  Total: {cost['total_production_cost']} {cost['currency']}")

    print("\n=== Margin Evaluation ===")
    margin = me.evaluate_margin(None, "led_sign", 450, "USD", "US")
    print(f"  Revenue: ${margin['revenue']['usd_value']}")
    print(f"  Cost: ${margin['cost']['total_cost']}")
    print(f"  Net Margin: ${margin['margin']['net']} ({margin['margin']['net_rate']}%)")
    print(f"  Adequate: {margin['target']['margin_adequate']}")

    print("\n=== Optimize Price ===")
    opt = me.optimize_price(None, "led_sign", "DE")
    print(f"  Suggested: ${opt['price_tiers']['suggested_price']}")
    print(f"  Margin at suggested: {opt['margin_at_suggested']}%")

    print("\n=== Profit Summary ===")
    summary = me.get_profit_summary()
    print(f"  Revenue: {summary['total_revenue']}")
    print(f"  Profit Rate: {summary['profit_rate']}%")
