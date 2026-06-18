"""Budget Controller — 预算控制

预算设置 + vs-actual 对比 + 超支预警。
"""

import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class BudgetEngine:
    """预算控制引擎"""

    CATEGORIES = [
        "operation", "marketing", "shipping", "commission",
        "salary", "office", "travel", "maintenance", "other",
        "product_sales", "service", "materials", "labor",
    ]

    def _import_db(self):
        sys.path.insert(0, BASE_DIR)
        import database as db_mod
        return db_mod

    def set_budget(self, period, category, amount, notes=""):
        """设置预算"""
        if category not in self.CATEGORIES:
            return {"error": f"Invalid category: {category}"}
        db = self._import_db()
        bid = db.set_budget({
            "period": period,
            "category": category,
            "amount": amount,
            "notes": notes,
        })
        if bid:
            return {"id": bid, "period": period, "category": category, "amount": amount}
        return {"error": "Failed to set budget"}

    def get_budgets(self, period=None, category=None):
        """获取预算"""
        db = self._import_db()
        return db.get_budgets(period, category)

    def get_budget_vs_actual(self, period):
        """预算 vs 实际对比"""
        db = self._import_db()
        budgets = db.get_budgets(period=period)

        # 解析期间的年月
        # period 格式: YYYY-MM
        try:
            year, month = period.split("-")
            start_date = f"{period}-01"
            if month == "12":
                end_date = f"{int(year)+1}-01-01"
            else:
                end_date = f"{year}-{int(month)+1:02d}-01"
        except Exception:
            start_date = f"{period}-01"
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 实际数据：从 orders 和 expenses 聚合
        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))
        conn.row_factory = sqlite3.Row

        # orders 收入（按产品类别）
        order_revenue = dict(conn.execute(
            """SELECT COALESCE(p.category, 'product_sales') as cat,
                      COALESCE(SUM(o.total_amount), 0) as total
               FROM orders o
               LEFT JOIN products p ON o.id = p.id
               WHERE o.status NOT IN ('cancelled', 'lost')
                 AND o.created_at >= ? AND o.created_at < ?
               GROUP BY cat""",
            (start_date, end_date)
        ).fetchall())

        # 费用
        expense_actuals = dict(conn.execute(
            """SELECT category, COALESCE(SUM(amount), 0) as total
               FROM expenses
               WHERE status='approved'
                 AND expense_date >= ? AND expense_date < ?
               GROUP BY category""",
            (start_date, end_date)
        ).fetchall())

        conn.close()

        # 映射 expenses → budget categories
        actual_map = {}
        for cat, total in expense_actuals.items():
            actual_map[cat] = float(total)

        # 映射 orders → budget categories
        for cat, total in order_revenue.items():
            actual_map[cat] = actual_map.get(cat, 0) + float(total)

        results = []
        for b in budgets:
            cat = b["category"]
            budgeted = float(b["planned_amount"])
            actual = actual_map.get(cat, 0)
            variance = round(actual - budgeted, 2)
            variance_pct = round(variance / budgeted * 100, 1) if budgeted > 0 else 0

            if variance_pct > 10:
                status = "over_budget"
            elif variance_pct < -10:
                status = "under_budget"
            else:
                status = "on_track"

            results.append({
                "id": b["id"],
                "category": cat,
                "budgeted": round(budgeted, 2),
                "actual": round(actual, 2),
                "variance": variance,
                "variance_pct": variance_pct,
                "status": status,
            })

        return sorted(results, key=lambda x: abs(x["variance_pct"]), reverse=True)

    def get_budget_alerts(self, threshold_pct=10):
        """获取超支预警"""
        db = self._import_db()
        periods = db.get_budgets()
        period_set = set(b["period"] for b in periods)

        alerts = []
        for period in sorted(period_set):
            vs = self.get_budget_vs_actual(period)
            for item in vs:
                if item["status"] == "over_budget" and item["variance_pct"] > threshold_pct:
                    alerts.append({
                        "period": period,
                        "category": item["category"],
                        "budgeted": item["budgeted"],
                        "actual": item["actual"],
                        "variance": item["variance"],
                        "variance_pct": item["variance_pct"],
                        "severity": "high" if item["variance_pct"] > 30 else "medium",
                    })

        return sorted(alerts, key=lambda x: -x["variance_pct"])

    def auto_generate_months(self, year, months):
        """自动生成指定年月预算空行"""
        db = self._import_db()
        count = 0
        for m in range(1, months + 1):
            period = f"{year}-{m:02d}"
            for cat in self.CATEGORIES:
                existing = db.get_budgets(period=period, category=cat)
                if not existing:
                    db.set_budget({
                        "period": period,
                        "category": cat,
                        "amount": 0,
                        "notes": "auto-generated",
                    })
                    count += 1
        return count


# ==================== 测试 ====================
if __name__ == "__main__":
    e = BudgetEngine()

    print("=== Set Budget ===")
    r = e.set_budget("2026-06", "marketing", 2000, "June marketing budget")
    print(f"  {r}")

    r = e.set_budget("2026-06", "operation", 1000)
    print(f"  {r}")

    r = e.set_budget("2026-06", "shipping", 1500)
    print(f"  {r}")

    print("\n=== Budget vs Actual (2026-06) ===")
    vs = e.get_budget_vs_actual("2026-06")
    for item in vs:
        print(f"  {item['category']}: budget={item['budgeted']} actual={item['actual']} "
              f"var={item['variance_pct']}% [{item['status']}]")

    print("\n=== Alerts ===")
    alerts = e.get_budget_alerts()
    for a in alerts:
        print(f"  [{a['severity']}] {a['period']} {a['category']}: {a['variance_pct']}% over")
    if not alerts:
        print("  (none)")

    print("\n=== Auto-generate 2026-07 ===")
    cnt = e.auto_generate_months(2026, 7)
    print(f"  Generated {cnt} budget placeholders")
