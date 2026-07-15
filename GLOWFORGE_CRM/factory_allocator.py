"""Factory Allocator — 工厂分配器（V5）

多工厂订单分配：根据目的地、产品类型、成本偏好
自动选择最优工厂进行生产。
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 默认工厂定义
_DEFAULT_FACTORIES = [
    {
        "name": "Bohui HQ Factory (Shenzhen)",
        "location": "Shenzhen, China",
        "capability_tags": ["led_sign", "neon_sign", "channel_letter", "lightbox",
                          "pylon_sign", "digital_display", "directory_sign",
                          "awning", "floor_sign", "window_sign", "general"],
        "max_capacity_monthly": 5000,
        "current_load": 0,
        "shipping_zones": ["NA", "EU", "APAC", "LATAM", "MEA"],
        "preferred_zones": ["APAC", "NA"],
        "base_currency": "CNY",
    },
    {
        "name": "Bohui EU Warehouse (Rotterdam)",
        "location": "Rotterdam, Netherlands",
        "capability_tags": ["led_sign", "neon_sign", "channel_letter", "lightbox",
                          "directory_sign", "floor_sign", "window_sign", "general"],
        "max_capacity_monthly": 2000,
        "current_load": 0,
        "shipping_zones": ["EU", "MEA"],
        "preferred_zones": ["EU"],
        "base_currency": "EUR",
    },
]

# 预估运费（USD）
_SHIPPING_ESTIMATES = {
    "NA": {"sea": 1500, "air": 4500, "sea_days": 25, "air_days": 5, "express_days": 3},
    "EU": {"sea": 1800, "air": 5000, "sea_days": 30, "air_days": 5, "express_days": 3},
    "APAC": {"sea": 500, "air": 2000, "sea_days": 10, "air_days": 3, "express_days": 1},
    "LATAM": {"sea": 2500, "air": 6000, "sea_days": 35, "air_days": 7, "express_days": 4},
    "MEA": {"sea": 2800, "air": 5500, "sea_days": 28, "air_days": 6, "express_days": 4},
}


class FactoryAllocator:
    """工厂分配器"""

    def get_all_factories(self) -> list:
        """获取所有工厂

        Returns:
            list: [{id, name, location, capability_tags, ...}]
        """
        results = []
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute("SELECT * FROM factories ORDER BY name").fetchall()
            conn.close()
            for r in rows:
                factory = dict(r)
                if isinstance(factory.get("capability_tags"), str):
                    factory["capability_tags"] = json.loads(factory["capability_tags"])
                if isinstance(factory.get("shipping_zones"), str):
                    factory["shipping_zones"] = json.loads(factory["shipping_zones"])
                results.append(factory)
        except Exception:
            pass

        if not results:
            for i, f in enumerate(_DEFAULT_FACTORIES):
                results.append({
                    "id": i + 1,
                    "name": f["name"],
                    "location": f["location"],
                    "capability_tags": f["capability_tags"],
                    "max_capacity_monthly": f["max_capacity_monthly"],
                    "current_load": f["current_load"],
                    "shipping_zones": f["shipping_zones"],
                    "base_currency": f["base_currency"],
                })

        return results

    def find_best_factory(self, product_category: str,
                          destination_country: str,
                          preference: str = "cost") -> dict:
        """寻找最优工厂

        Args:
            product_category: 产品类别
            destination_country: 目的地国家代码
            preference: 优化偏好（cost/ speed / balanced）

        Returns:
            dict: {factory, reason, shipping, total_cost, days}
        """
        factories = self.get_all_factories()
        if not factories:
            return {"error": "No factories available"}

        # 确定目标区域
        try:
            from region_engine import RegionEngine
            region_info = RegionEngine().get_region_for_country(destination_country)
            dest_region = region_info["code"]
        except Exception:
            dest_region = "APAC"

        cat = product_category.lower().strip()
        candidates = []

        for factory in factories:
            tags = factory.get("capability_tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags)
            zones = factory.get("shipping_zones", [])
            if isinstance(zones, str):
                zones = json.loads(zones)

            # 检查能否生产该产品
            if cat not in tags and "general" not in tags:
                continue
            # 检查能否发货到该区域
            if dest_region not in zones:
                continue

            # 计算成本
            shipping_info = self.estimate_shipping(destination_country)
            ship_cost = shipping_info.get("cost_sea", 9999)
            ship_days = shipping_info.get("days_sea", 30)

            # 产能利用率
            max_cap = factory.get("max_capacity_monthly", 1000)
            current = factory.get("current_load", 0)
            load_rate = current / max_cap if max_cap > 0 else 1

            # 成本评分（越低越好）
            cost_score = ship_cost * (1 + load_rate * 0.5)
            # 速度评分（越高越好）
            speed_score = 100 / max(ship_days, 1)
            # 综合评分
            balanced_score = (cost_score * 0.6) + ((100 / speed_score) * 0.4) if speed_score > 0 else cost_score

            candidates.append({
                "factory": factory,
                "shipping_cost": ship_cost,
                "shipping_days": ship_days,
                "load_rate": round(load_rate * 100, 1),
                "cost_score": round(cost_score, 2),
                "speed_score": round(speed_score, 2),
                "balanced_score": round(balanced_score, 2),
            })

        if not candidates:
            return {"error": f"No factory can produce '{cat}' for {destination_country}"}

        # 按偏好排序
        if preference == "cost":
            candidates.sort(key=lambda x: x["cost_score"])
        elif preference == "speed":
            candidates.sort(key=lambda x: -x["speed_score"])
        else:
            candidates.sort(key=lambda x: x["balanced_score"])

        best = candidates[0]
        factory = best["factory"]

        return {
            "factory": {
                "id": factory.get("id", 0),
                "name": factory["name"],
                "location": factory["location"],
            },
            "destination_country": destination_country,
            "destination_region": dest_region,
            "product_category": cat,
            "preference": preference,
            "shipping": {
                "mode": "sea",
                "cost": best["shipping_cost"],
                "days": best["shipping_days"],
            },
            "factory_load": best["load_rate"],
            "reason": (
                f"Selected {factory['name']} for {cat} → {destination_country} "
                f"({preference} optimization, shipping ${best['shipping_cost']}, "
                f"{best['shipping_days']} days)"
            ),
        }

    def estimate_shipping(self, destination_country: str,
                          volume_m3: float = 0.1,
                          mode: str = "sea") -> dict:
        """估算运费

        Args:
            destination_country: 目的地国家代码
            volume_m3: 体积（立方米）
            mode: sea / air / express

        Returns:
            dict: {cost, days, currency, mode}
        """
        try:
            from region_engine import RegionEngine
            region_info = RegionEngine().get_region_for_country(destination_country)
            region_code = region_info["code"]
        except Exception:
            region_code = "APAC"

        estimates = _SHIPPING_ESTIMATES.get(region_code, _SHIPPING_ESTIMATES["APAC"])

        if mode == "air":
            base_cost = estimates["air"]
            days = estimates["air_days"]
        elif mode == "express":
            base_cost = estimates["air"] * 1.5
            days = estimates["express_days"]
        else:
            base_cost = estimates["sea"]
            days = estimates["sea_days"]

        # 按体积调整
        cost = round(base_cost * (volume_m3 / 0.1), 2)

        return {
            "cost_sea": round(base_cost * (volume_m3 / 0.1), 2),
            "cost_air": round(estimates["air"] * (volume_m3 / 0.1), 2),
            "days_sea": estimates["sea_days"],
            "days_air": estimates["air_days"],
            "chosen_mode": mode,
            "chosen_cost": cost,
            "chosen_days": days,
            "volume_m3": volume_m3,
            "currency": "USD",
            "destination_region": region_code,
        }

    def get_factory_utilization(self) -> list:
        """获取各工厂产能利用率

        Returns:
            list: [{name, max_capacity, current_load, utilization_rate}]
        """
        results = []
        for factory in self.get_all_factories():
            max_cap = factory.get("max_capacity_monthly", 1000)
            current = factory.get("current_load", 0)
            rate = round(current / max_cap * 100, 1) if max_cap > 0 else 0
            results.append({
                "id": factory.get("id", 0),
                "name": factory["name"],
                "location": factory.get("location", ""),
                "max_capacity_monthly": max_cap,
                "current_load": current,
                "utilization_rate": rate,
                "status": "overloaded" if rate > 85 else ("busy" if rate > 60 else "available"),
            })
        return results

    def assign_order(self, factory_id: int, order_id: int) -> bool:
        """将订单分配给工厂（增加工厂负载）

        Returns:
            bool: 是否成功
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            # 增加负载
            conn.execute(
                "UPDATE factories SET current_load = current_load + 1 WHERE id=?",
                (factory_id,),
            )
            # 更新订单的 factory_id
            conn.execute(
                "UPDATE orders SET factory_id=? WHERE id=?",
                (factory_id, order_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False


# ==================== 测试 ====================
if __name__ == "__main__":
    fa = FactoryAllocator()

    print("=== All Factories ===")
    for f in fa.get_all_factories():
        print(f"  {f.get('id')}: {f['name']} ({f['location']})")
        print(f"    Capabilities: {f.get('capability_tags', [])}")

    print("\n=== Best Factory ===")
    best = fa.find_best_factory("led_sign", "US", preference="cost")
    print(f"  {best.get('factory', {}).get('name', '?')}")
    print(f"  Reason: {best.get('reason', '?')}")

    print("\n=== Best Factory (EU delivery) ===")
    best2 = fa.find_best_factory("neon_sign", "DE", preference="cost")
    print(f"  {best2.get('factory', {}).get('name', '?')}")
    print(f"  Reason: {best2.get('reason', '?')}")

    print("\n=== Shipping Estimate ===")
    for country, vol in [("US", 0.1), ("DE", 0.2), ("JP", 0.15)]:
        ship = fa.estimate_shipping(country, vol)
        print(f"  {country}: sea=${ship['cost_sea']} ({ship['days_sea']}d), "
              f"air=${ship['cost_air']} ({ship['days_air']}d)")

    print("\n=== Factory Utilization ===")
    for u in fa.get_factory_utilization():
        print(f"  {u['name']}: {u['utilization_rate']}% ({u['status']})")
