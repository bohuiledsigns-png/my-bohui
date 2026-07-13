"""Revenue Dashboard V5 — 跨市场收入仪表盘

按区域、币种、工厂维度聚合业务数据，
提供全球收入、利润、产能利用率的可视化数据源。
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class RevenueDashboardV5:
    """V5 跨市场收入仪表盘"""

    def get_revenue_by_region(self, days: int = 30) -> list:
        """按区域聚合收入

        Returns:
            list: [{region_code, region_name, revenue, orders, avg_order_value}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT r.code, r.name,
                          COALESCE(SUM(o.total_amount), 0) as revenue,
                          COUNT(o.id) as orders
                   FROM orders o
                   JOIN regions r ON o.region_id = r.id
                   WHERE o.created_at >= datetime('now', ? || ' days')
                     AND o.status NOT IN ('cancelled', 'lost')
                   GROUP BY r.code, r.name
                   ORDER BY revenue DESC""",
                (f"-{days}",),
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                rev = float(r["revenue"])
                cnt = r["orders"]
                results.append({
                    "region_code": r["code"],
                    "region_name": r["name"],
                    "revenue": rev,
                    "orders": cnt,
                    "avg_order_value": round(rev / cnt, 2) if cnt > 0 else 0,
                })
            return results
        except Exception:
            return []

    def get_profit_margin_by_region(self, days: int = 30) -> list:
        """按区域聚合利润

        Returns:
            list: [{region_code, region_name, revenue, cost, profit, margin_rate}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT r.code, r.name,
                          COALESCE(SUM(o.total_amount), 0) as revenue,
                          COALESCE(SUM(o.production_cost + o.shipping_cost + o.platform_fee), 0) as total_cost,
                          COALESCE(SUM(o.net_profit), 0) as profit
                   FROM orders o
                   JOIN regions r ON o.region_id = r.id
                   WHERE o.created_at >= datetime('now', ? || ' days')
                     AND o.status NOT IN ('cancelled', 'lost')
                   GROUP BY r.code, r.name
                   ORDER BY profit DESC""",
                (f"-{days}",),
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                rev = float(r["revenue"])
                cost = float(r["total_cost"])
                profit = float(r["profit"])
                results.append({
                    "region_code": r["code"],
                    "region_name": r["name"],
                    "revenue": rev,
                    "total_cost": round(cost, 2),
                    "profit": profit,
                    "margin_rate": round(profit / rev * 100, 1) if rev > 0 else 0,
                })
            return results
        except Exception:
            return []

    def get_factory_utilization(self) -> list:
        """获取工厂产能利用率

        Returns:
            list: [{name, max_capacity, current_load, utilization_rate, status}]
        """
        try:
            from factory_allocator import FactoryAllocator
            return FactoryAllocator().get_factory_utilization()
        except Exception:
            return []

    def get_multi_currency_revenue(self, days: int = 30) -> list:
        """按币种聚合收入

        Returns:
            list: [{currency, total_amount, order_count}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT COALESCE(o.currency, 'USD') as currency,
                          COALESCE(SUM(o.total_amount), 0) as total,
                          COUNT(o.id) as orders
                   FROM orders o
                   WHERE o.created_at >= datetime('now', ? || ' days')
                     AND o.status NOT IN ('cancelled', 'lost')
                   GROUP BY o.currency
                   ORDER BY total DESC""",
                (f"-{days}",),
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                results.append({
                    "currency": r["currency"],
                    "total_amount": float(r["total"]),
                    "order_count": r["orders"],
                })
            return results
        except Exception:
            return []

    def get_global_kpi_summary(self) -> dict:
        """全球KPI汇总

        Returns:
            dict: 包含全局汇总指标
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()

            # 总收入（USD）
            revenue_row = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status NOT IN ('cancelled', 'lost')"
            ).fetchone()[0]

            # 总利润
            profit_row = conn.execute(
                "SELECT COALESCE(SUM(net_profit), 0) FROM orders WHERE status NOT IN ('cancelled', 'lost')"
            ).fetchone()[0]

            # 总客户数
            total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

            # 总订单数
            total_orders = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status NOT IN ('cancelled', 'lost')"
            ).fetchone()[0]

            # 区域数量
            region_count = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]

            # 工厂数量
            factory_count = conn.execute("SELECT COUNT(*) FROM factories").fetchone()[0]

            # Agent数量
            agent_count = conn.execute("SELECT COUNT(*) FROM agent_profiles").fetchone()[0]

            # 各区域客户数
            region_customers = conn.execute(
                """SELECT r.code, COUNT(c.id) as cnt
                   FROM customers c
                   JOIN regions r ON c.region_id = r.id
                   WHERE c.region_id IS NOT NULL
                   GROUP BY r.code"""
            ).fetchall()

            # 最近30天趋势
            trend = conn.execute(
                """SELECT date(created_at) as day,
                          COALESCE(SUM(total_amount), 0) as revenue
                   FROM orders
                   WHERE created_at >= datetime('now', '-30 days')
                     AND status NOT IN ('cancelled', 'lost')
                   GROUP BY date(created_at)
                   ORDER BY day"""
            ).fetchall()

            conn.close()

            revenue = float(revenue_row)
            profit = float(profit_row)

            return {
                "total_revenue": revenue,
                "total_profit": profit,
                "profit_margin": round(profit / revenue * 100, 1) if revenue > 0 else 0,
                "total_customers": total_customers,
                "total_orders": total_orders,
                "regions": region_count,
                "factories": factory_count,
                "agents": agent_count,
                "region_customer_distribution": [
                    {"code": r["code"], "count": r["cnt"]} for r in region_customers
                ],
                "revenue_trend": [
                    {"date": r["day"], "revenue": float(r["revenue"])} for r in trend
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_region_lead_stats(self) -> list:
        """各区域线索统计

        Returns:
            list: [{region_code, region_name, total_leads, contacted, converted}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT r.code, r.name,
                          COUNT(c.id) as total,
                          SUM(CASE WHEN c.lead_status IN ('contacted','qualified','negotiating','hot','customer') THEN 1 ELSE 0 END) as contacted,
                          SUM(CASE WHEN c.lead_status='customer' THEN 1 ELSE 0 END) as converted
                   FROM customers c
                   JOIN regions r ON c.region_id = r.id
                   WHERE c.region_id IS NOT NULL
                   GROUP BY r.code, r.name
                   ORDER BY total DESC"""
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                total = r["total"]
                contacted = r["contacted"]
                converted = r["converted"]
                results.append({
                    "region_code": r["code"],
                    "region_name": r["name"],
                    "total_leads": total,
                    "contacted": contacted,
                    "converted": converted,
                    "contact_rate": round(contacted / total * 100, 1) if total > 0 else 0,
                    "conversion_rate": round(converted / contacted * 100, 1) if contacted > 0 else 0,
                })
            return results
        except Exception:
            return []

    def get_global_performance_ranking(self) -> list:
        """全球绩效排名（区域维度）

        Returns:
            list: [{region, revenue, profit, margin_rate, leads, conversion}]
        """
        revenue_data = self.get_revenue_by_region()
        profit_data = self.get_profit_margin_by_region()
        lead_data = self.get_region_lead_stats()

        # 合并
        ranking = {}
        for item in revenue_data:
            code = item["region_code"]
            ranking[code] = {
                "region_code": code,
                "region_name": item["region_name"],
                "revenue": item["revenue"],
                "orders": item["orders"],
                "avg_order_value": item["avg_order_value"],
            }
        for item in profit_data:
            code = item["region_code"]
            if code in ranking:
                ranking[code]["profit"] = item["profit"]
                ranking[code]["total_cost"] = item["total_cost"]
                ranking[code]["margin_rate"] = item["margin_rate"]
        for item in lead_data:
            code = item["region_code"]
            if code in ranking:
                ranking[code]["total_leads"] = item["total_leads"]
                ranking[code]["contacted"] = item["contacted"]
                ranking[code]["converted"] = item["converted"]
                ranking[code]["conversion_rate"] = item["conversion_rate"]

        sorted_ranking = sorted(
            ranking.values(),
            key=lambda x: x.get("revenue", 0),
            reverse=True,
        )
        return sorted_ranking


# ==================== 测试 ====================
if __name__ == "__main__":
    d = RevenueDashboardV5()

    print("=== Global KPI Summary ===")
    kpi = d.get_global_kpi_summary()
    for k, v in kpi.items():
        if k != "revenue_trend" and k != "region_customer_distribution":
            print(f"  {k}: {v}")

    print("\n=== Revenue by Region ===")
    for r in d.get_revenue_by_region():
        print(f"  {r['region_code']}: ${r['revenue']} ({r['orders']} orders)")

    print("\n=== Profit Margin by Region ===")
    for r in d.get_profit_margin_by_region():
        print(f"  {r['region_code']}: {r['margin_rate']}%")

    print("\n=== Multi-Currency Revenue ===")
    for r in d.get_multi_currency_revenue():
        print(f"  {r['currency']}: {r['total_amount']} ({r['order_count']} orders)")

    print("\n=== Region Lead Stats ===")
    for r in d.get_region_lead_stats():
        print(f"  {r['region_code']}: {r['total_leads']} leads, {r['conversion_rate']}% conv")

    print("\n=== Global Performance Ranking ===")
    for r in d.get_global_performance_ranking():
        print(f"  {r['region_code']}: rev=${r.get('revenue',0)}, margin={r.get('margin_rate',0)}%, "
              f"conv={r.get('conversion_rate',0)}%")
