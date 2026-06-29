"""Production Allocator — 工厂产能分配系统

订单不再"乱排"，而是按国家+利润+紧急程度排序。

排序优先级：
  1. 利润金额 (高→低)
  2. 紧急程度 (high > medium > low)
  3. 客户等级 (A > B > C)
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class ProductionAllocator:
    """产能分配系统 — 智能排产"""

    # 工厂配置
    FACTORIES = {
        "f1": {
            "id": "f1",
            "name": "Main Factory (Shenzhen)",
            "capacity_daily": 100,
            "specialization": ["luminous_sign", "led_display"],
            "base_cost_multiplier": 1.0,
            "location": "Shenzhen, China",
            "shipping_zones": ["APAC", "NA", "EU"],
        },
        "f2": {
            "id": "f2",
            "name": "Premium Workshop (Dongguan)",
            "capacity_daily": 40,
            "specialization": ["premium_sign", "luxury_install"],
            "base_cost_multiplier": 1.3,
            "location": "Dongguan, China",
            "shipping_zones": ["MEA", "EU"],
        },
        "f3": {
            "id": "f3",
            "name": "Quick Production Line",
            "capacity_daily": 60,
            "specialization": ["standard_sign", "acrylic"],
            "base_cost_multiplier": 0.85,
            "location": "Shenzhen, China",
            "shipping_zones": ["APAC"],
        },
    }

    @staticmethod
    def allocate(orders: list) -> dict:
        """将订单分配到工厂并排序

        Args:
            orders: [{
                order_id, country, profit_amount, urgency,
                product_type, customer_priority, quantity
            }, ...]

        Returns:
            dict: {
                queue: [排序后的订单],
                factory_assignments: {factory_id: [orders]},
                total_profit, total_orders,
            }
        """
        if not orders:
            return {"queue": [], "factory_assignments": {}, "total_profit": 0, "total_orders": 0}

        # 1. 利润排序（主要）
        # 2. 紧急程度（次要）
        # 3. 客户等级（第三）
        urgency_weight = {"high": 100, "medium": 50, "low": 0}
        priority_weight = {"A": 100, "B": 50, "C": 0}

        scored_orders = []
        for order in orders:
            profit = order.get("profit_amount", 0) or order.get("price", 0) * 0.3
            urgency = urgency_weight.get(order.get("urgency", "medium"), 50)
            priority = priority_weight.get(order.get("customer_priority", "C"), 0)
            # 综合得分：利润占60%，紧急30%，优先级10%
            score = profit * 0.6 + urgency * 3 + priority * 1
            scored_orders.append({**order, "_score": score})

        # 按得分降序
        scored_orders.sort(key=lambda x: x["_score"], reverse=True)

        # 分配到工厂
        factory_assignments = {fid: [] for fid in ProductionAllocator.FACTORIES}
        remaining = list(scored_orders)

        for fid, factory in ProductionAllocator.FACTORIES.items():
            capacity = factory["capacity_daily"]
            assigned = []
            still_remaining = []
            for order in remaining:
                if len(assigned) >= capacity:
                    still_remaining.append(order)
                    continue
                # 检查产品类型是否匹配
                product_type = order.get("product_type", "general")
                if product_type in factory["specialization"] or "general" in factory["specialization"]:
                    assigned.append(order)
                else:
                    still_remaining.append(order)
            factory_assignments[fid] = assigned
            remaining = still_remaining

        # 未分配订单
        if remaining:
            factory_assignments["unassigned"] = remaining

        total_profit = sum(
            o.get("profit_amount", 0) or o.get("price", 0) * 0.3
            for o in scored_orders
        )

        return {
            "queue": scored_orders,
            "factory_assignments": {
                fid: [
                    {"order_id": o.get("order_id", f"#{i}"), "profit": o.get("profit_amount", 0),
                     "country": o.get("country", ""), "urgency": o.get("urgency", "medium"),
                     "score": o["_score"]}
                    for i, o in enumerate(orders)
                ]
                for fid, orders in factory_assignments.items()
                if orders
            },
            "total_profit": round(total_profit, 2),
            "total_orders": len(scored_orders),
            "unassigned_count": len(remaining),
        }

    @staticmethod
    def get_factory_utilization() -> list:
        """获取工厂当前利用率

        Returns:
            list: [{factory_id, name, capacity, utilization_pct, load}]
        """
        # 在实际应用中从数据库读取
        return [
            {
                "factory_id": fid,
                "name": f["name"],
                "capacity_daily": f["capacity_daily"],
                "specialization": f["specialization"],
                "shipping_zones": f["shipping_zones"],
                "base_cost_multiplier": f["base_cost_multiplier"],
            }
            for fid, f in ProductionAllocator.FACTORIES.items()
        ]

    @staticmethod
    def estimate_shipping(country: str, factory_id: str = "f1",
                          quantity: int = 1, weight_kg: float = 10) -> dict:
        """估算运费

        Args:
            country: 目标国家
            factory_id: 工厂ID
            quantity: 数量
            weight_kg: 重量(kg)

        Returns:
            dict: {shipping_cost, currency, estimated_days, notes}
        """
        factory = ProductionAllocator.FACTORIES.get(factory_id, ProductionAllocator.FACTORIES["f1"])

        # 区域运费估算（简化）
        zone_shipping = {
            "NA": {"base": 80, "per_kg": 5, "days": "7-12"},
            "EU": {"base": 90, "per_kg": 6, "days": "10-15"},
            "MEA": {"base": 100, "per_kg": 7, "days": "10-18"},
            "APAC": {"base": 30, "per_kg": 3, "days": "3-7"},
            "LATAM": {"base": 120, "per_kg": 8, "days": "12-20"},
        }

        # 确定区域
        try:
            from global_router import GlobalRouter
            region = GlobalRouter.get_region_for_country(country)
            region_code = region.get("region", "APAC")
        except Exception:
            region_code = "APAC"

        shipping_info = zone_shipping.get(region_code, zone_shipping["APAC"])
        cost = round((shipping_info["base"] + shipping_info["per_kg"] * weight_kg) * quantity, 2)

        return {
            "shipping_cost": cost,
            "currency": "USD",
            "estimated_days": shipping_info["days"],
            "factory": factory["name"],
            "destination_region": region_code,
            "weight_kg": weight_kg,
            "quantity": quantity,
        }


# 快捷入口
allocator = ProductionAllocator()


def allocate_orders(orders: list) -> dict:
    return ProductionAllocator.allocate(orders)


def estimate_shipping(country: str, **kwargs) -> dict:
    return ProductionAllocator.estimate_shipping(country, **kwargs)
