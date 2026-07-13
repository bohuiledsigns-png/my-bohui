"""P&L Engine — 损益引擎

会计科目表 + 会计期间 + 损益表生成 + 维度钻取 + 环比分析。
"""

import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class PLEngine:
    """损益引擎"""

    ACCOUNTS = [
        {"code": "4100", "name": "产品销售-发光字", "type": "revenue", "category": "product_sales"},
        {"code": "4200", "name": "产品销售-炫彩字", "type": "revenue", "category": "product_sales"},
        {"code": "4300", "name": "安装服务收入", "type": "revenue", "category": "service"},
        {"code": "5100", "name": "原材料成本", "type": "cogs", "category": "materials"},
        {"code": "5200", "name": "人工成本", "type": "cogs", "category": "labor"},
        {"code": "5300", "name": "物流成本", "type": "cogs", "category": "shipping"},
        {"code": "5305", "name": "平台手续费", "type": "cogs", "category": "fees"},
        {"code": "6100", "name": "B2B平台费用", "type": "expense", "category": "marketing"},
        {"code": "6200", "name": "广告投放", "type": "expense", "category": "marketing"},
        {"code": "6300", "name": "销售佣金", "type": "expense", "category": "commission"},
        {"code": "7100", "name": "办公运营", "type": "expense", "category": "operation"},
        {"code": "7200", "name": "工资社保", "type": "expense", "category": "operation"},
        {"code": "7300", "name": "差旅费用", "type": "expense", "category": "travel"},
        {"code": "7400", "name": "设备维护", "type": "expense", "category": "maintenance"},
    ]

    def _import_db(self):
        sys.path.insert(0, BASE_DIR)
        import database as db_mod
        return db_mod

    def seed_accounts(self):
        """初始化会计科目表"""
        db = self._import_db()
        count = 0
        for i, acct in enumerate(self.ACCOUNTS):
            existing = db.get_pl_accounts(active_only=False)
            if not any(a["code"] == acct["code"] for a in existing):
                db.add_pl_account({
                    **acct,
                    "description": "",
                    "sort_order": (i + 1) * 10,
                })
                count += 1
        return count

    def get_periods(self):
        """获取所有会计期间"""
        db = self._import_db()
        return db.get_pl_periods()

    def create_period(self, code, ptype, start_date, end_date, notes=""):
        """创建会计期间"""
        db = self._import_db()
        pid = db.add_pl_period({
            "period_code": code,
            "type": ptype,
            "start_date": start_date,
            "end_date": end_date,
            "notes": notes,
        })
        return {"id": pid, "period_code": code}

    def close_period(self, period_id):
        """关账"""
        db = self._import_db()
        db.close_pl_period(period_id)
        return {"status": "closed", "period_id": period_id}

    def generate_pl(self, period_id):
        """生成损益表：从 orders 自动聚合 + pl_entries 补充"""
        db = self._import_db()
        period = db.get_pl_period(period_id)
        if not period:
            return {"error": "Period not found"}

        revenue = 0.0
        cogs = 0.0
        gross_profit = 0.0
        total_expenses = 0.0
        accounts_data = {}

        # 获取会计科目
        accounts = db.get_pl_accounts()
        acct_map = {a["code"]: a for a in accounts}

        # 从 orders 聚合（已完成的订单）
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        orders = conn.execute(
            """SELECT id, total_amount, production_cost, shipping_cost, platform_fee,
                      net_profit, COALESCE(tax_amount, 0) as tax_amount
               FROM orders
               WHERE status NOT IN ('cancelled', 'lost', 'pending_approval')
                 AND created_at >= ? AND created_at <= ?""",
            (period["start_date"], period["end_date"] + " 23:59:59")
        ).fetchall()

        pl_entry_data = []
        for o in orders:
            rev = float(o["total_amount"] or 0) - float(o["tax_amount"] or 0)
            pc = float(o["production_cost"] or 0)
            sc = float(o["shipping_cost"] or 0)
            pf = float(o["platform_fee"] or 0)
            total_cogs = pc + sc + pf

            # 收入科目 4100
            pl_entry_data.append({"account_code": "4100", "amount": rev, "order_id": o["id"]})
            # 原材料成本 5100
            if pc > 0:
                pl_entry_data.append({"account_code": "5100", "amount": pc, "order_id": o["id"]})
            # 物流成本 5300
            if sc > 0:
                pl_entry_data.append({"account_code": "5300", "amount": sc, "order_id": o["id"]})
            # 平台手续费 5305
            if pf > 0:
                pl_entry_data.append({"account_code": "5305", "amount": pf, "order_id": o["id"]})

        # 从 pl_entries 获取 adjustment 条目
        adjustments = conn.execute(
            "SELECT pe.amount, a.code as account_code FROM pl_entries pe "
            "LEFT JOIN pl_accounts a ON pe.account_id=a.id "
            "WHERE pe.period_id=? AND pe.entry_type='adjustment'",
            (period_id,)
        ).fetchall()

        # 从 expense_engine 获取已审批费用
        try:
            from expense_engine import ExpenseEngine
            expenses = ExpenseEngine().get_expenses_approved(period["start_date"], period["end_date"] + " 23:59:59")
            for exp in expenses:
                # 映射 expenses.category → pl_accounts 费用科目
                cat_map = {
                    "operation": "7100", "marketing": "6100", "shipping": "5300",
                    "commission": "6300", "salary": "7200", "office": "7100",
                    "travel": "7300", "maintenance": "7400",
                }
                acct_code = cat_map.get(exp["category"], "7100")
                pl_entry_data.append({"account_code": acct_code, "amount": float(exp["amount"]), "order_id": None})
        except Exception:
            pass

        conn.close()

        # 聚合到科目
        acct_totals = {}
        for entry in pl_entry_data:
            code = entry["account_code"]
            acct_totals[code] = acct_totals.get(code, 0) + entry["amount"]

        for adj in adjustments:
            code = adj["account_code"]
            acct_totals[code] = acct_totals.get(code, 0) + float(adj["amount"])

        # 分类汇总
        by_category = {}
        for code, amount in sorted(acct_totals.items()):
            acct = acct_map.get(code, {})
            atype = acct.get("type", "expense")
            category = acct.get("category", "other")

            accounts_data[code] = {
                "code": code,
                "name": acct.get("name", code),
                "type": atype,
                "category": category,
                "amount": round(amount, 2),
            }

            if atype == "revenue":
                revenue += amount
            elif atype == "cogs":
                cogs += amount
            elif atype == "expense":
                total_expenses += amount

            by_category[category] = by_category.get(category, 0) + amount

        gross_profit = revenue - cogs
        net_profit = gross_profit - total_expenses
        net_margin = round(net_profit / revenue * 100, 1) if revenue > 0 else 0
        gross_margin = round(gross_profit / revenue * 100, 1) if revenue > 0 else 0

        return {
            "period": period,
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin": gross_margin,
            "total_expenses": round(total_expenses, 2),
            "net_profit": round(net_profit, 2),
            "net_margin": net_margin,
            "accounts": [v for v in sorted(accounts_data.values(), key=lambda x: x["code"])],
            "by_category": [{"category": k, "amount": round(v, 2)} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
        }

    def get_pl_trend(self, months=6):
        """获取 P&L 趋势（按月）"""
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT strftime('%Y-%m', created_at) as month,
                      COALESCE(SUM(total_amount), 0) as revenue,
                      COALESCE(SUM(production_cost), 0) + COALESCE(SUM(shipping_cost), 0) + COALESCE(SUM(platform_fee), 0) as cogs,
                      COALESCE(SUM(net_profit), 0) as net_profit
               FROM orders
               WHERE status NOT IN ('cancelled', 'lost')
                 AND created_at >= datetime('now', ? || ' months')
               GROUP BY strftime('%Y-%m', created_at)
               ORDER BY month""",
            (f"-{months}",)
        ).fetchall()

        conn.close()

        result = []
        for r in rows:
            revenue = float(r["revenue"])
            cogs = float(r["cogs"])
            np_val = float(r["net_profit"])
            result.append({
                "month": r["month"],
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "net_profit": round(np_val, 2),
                "margin": round(np_val / revenue * 100, 1) if revenue > 0 else 0,
            })

        return result

    def get_pl_by_dimension(self, period_id, dimension="category"):
        """按维度钻取损益

        dimension: category (产品线), region (区域), country (国家)
        """
        db = self._import_db()
        period = db.get_pl_period(period_id)
        if not period:
            return []

        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if dimension == "category":
            # 按产品线
            rows = conn.execute(
                """SELECT COALESCE(p.category, 'uncategorized') as dim,
                          COUNT(DISTINCT o.id) as order_count,
                          COALESCE(SUM(o.total_amount), 0) as revenue,
                          COALESCE(SUM(o.production_cost), 0) + COALESCE(SUM(o.shipping_cost), 0) as total_cost,
                          COALESCE(SUM(o.net_profit), 0) as profit
                   FROM orders o
                   LEFT JOIN products p ON o.id = p.id
                   WHERE o.status NOT IN ('cancelled', 'lost')
                     AND o.created_at >= ? AND o.created_at <= ?
                   GROUP BY dim ORDER BY revenue DESC""",
                (period["start_date"], period["end_date"] + " 23:59:59")
            ).fetchall()

        elif dimension == "region":
            rows = conn.execute(
                """SELECT COALESCE(r.name, 'Unknown') as dim,
                          COUNT(DISTINCT o.id) as order_count,
                          COALESCE(SUM(o.total_amount), 0) as revenue,
                          COALESCE(SUM(o.production_cost), 0) + COALESCE(SUM(o.shipping_cost), 0) as total_cost,
                          COALESCE(SUM(o.net_profit), 0) as profit
                   FROM orders o
                   LEFT JOIN regions r ON o.region_id = r.id
                   WHERE o.status NOT IN ('cancelled', 'lost')
                     AND o.created_at >= ? AND o.created_at <= ?
                   GROUP BY dim ORDER BY revenue DESC""",
                (period["start_date"], period["end_date"] + " 23:59:59")
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT COALESCE(c.country, 'Unknown') as dim,
                          COUNT(DISTINCT o.id) as order_count,
                          COALESCE(SUM(o.total_amount), 0) as revenue,
                          COALESCE(SUM(o.production_cost), 0) + COALESCE(SUM(o.shipping_cost), 0) as total_cost,
                          COALESCE(SUM(o.net_profit), 0) as profit
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id = c.id
                   WHERE o.status NOT IN ('cancelled', 'lost')
                     AND o.created_at >= ? AND o.created_at <= ?
                   GROUP BY dim ORDER BY revenue DESC""",
                (period["start_date"], period["end_date"] + " 23:59:59")
            ).fetchall()

        conn.close()

        total_revenue = sum(float(r["revenue"]) for r in rows) or 1
        return [{
            "dimension": r["dim"],
            "order_count": r["order_count"],
            "revenue": round(float(r["revenue"]), 2),
            "total_cost": round(float(r["total_cost"]), 2),
            "profit": round(float(r["profit"]), 2),
            "margin": round(float(r["profit"]) / float(r["revenue"]) * 100, 1) if float(r["revenue"]) > 0 else 0,
            "revenue_share": round(float(r["revenue"]) / total_revenue * 100, 1),
        } for r in rows]

    def period_over_period(self, current_id, previous_id):
        """环比分析"""
        current = self.generate_pl(current_id)
        previous = self.generate_pl(previous_id)

        if "error" in current or "error" in previous:
            return {"error": "Invalid period"}

        def diff(cur, prev):
            if prev == 0:
                return {"current": cur, "previous": prev, "change": cur, "change_pct": None}
            return {
                "current": cur,
                "previous": prev,
                "change": round(cur - prev, 2),
                "change_pct": round((cur - prev) / prev * 100, 1),
            }

        return {
            "current_period": current["period"],
            "previous_period": previous["period"],
            "revenue": diff(current["revenue"], previous["revenue"]),
            "cogs": diff(current["cogs"], previous["cogs"]),
            "gross_profit": diff(current["gross_profit"], previous["gross_profit"]),
            "total_expenses": diff(current["total_expenses"], previous["total_expenses"]),
            "net_profit": diff(current["net_profit"], previous["net_profit"]),
            "gross_margin": {
                "current": current["gross_margin"],
                "previous": previous["gross_margin"],
                "change": round(current["gross_margin"] - previous["gross_margin"], 1),
            },
            "net_margin": {
                "current": current["net_margin"],
                "previous": previous["net_margin"],
                "change": round(current["net_margin"] - previous["net_margin"], 1),
            },
        }

    def get_margin_analysis(self, period_id):
        """毛利率分析"""
        pl = self.generate_pl(period_id)
        if "error" in pl:
            return {"error": pl["error"]}

        by_category = {}
        for acct in pl.get("accounts", []):
            cat = acct["category"]
            if cat not in by_category:
                by_category[cat] = {"revenue": 0, "cost": 0}
            if acct["type"] == "revenue":
                by_category[cat]["revenue"] += acct["amount"]
            elif acct["type"] == "cogs":
                by_category[cat]["cost"] += acct["amount"]

        cat_analysis = []
        for cat, vals in sorted(by_category.items(), key=lambda x: -x[1]["revenue"]):
            margin = round((vals["revenue"] - vals["cost"]) / vals["revenue"] * 100, 1) if vals["revenue"] > 0 else 0
            cat_analysis.append({
                "category": cat,
                "revenue": round(vals["revenue"], 2),
                "cost": round(vals["cost"], 2),
                "margin": margin,
            })

        return {
            "overall_gross_margin": pl["gross_margin"],
            "overall_net_margin": pl["net_margin"],
            "by_category": cat_analysis,
            "period": pl["period"],
        }


# ==================== 测试 ====================
if __name__ == "__main__":
    e = PLEngine()

    print("=== Seed Accounts ===")
    cnt = e.seed_accounts()
    print(f"  Seeded {cnt} new accounts")

    print("\n=== Create Period ===")
    now = datetime.now()
    ym = now.strftime("%Y-%m")
    r = e.create_period(f"{ym}-M", "monthly", now.strftime("%Y-%m-01"), now.strftime("%Y-%m-%d"))
    print(f"  Created: {r}")

    print("\n=== Periods ===")
    periods = e.get_periods()
    for p in periods:
        print(f"  {p['period_code']}: {p['start_date']} ~ {p['end_date']} closed={p['is_closed']}")

    if periods:
        pid = periods[0]["id"]
        print(f"\n=== P&L for period #{pid} ===")
        pl = e.generate_pl(pid)
        for k, v in pl.items():
            if k != "accounts" and k != "by_category" and k != "period":
                print(f"  {k}: {v}")
        print(f"  Accounts: {len(pl.get('accounts', []))} entries")
        print(f"  Categories: {len(pl.get('by_category', []))} entries")

        print(f"\n=== Trend (6 months) ===")
        trend = e.get_pl_trend(6)
        for t in trend:
            print(f"  {t['month']}: rev={t['revenue']} profit={t['net_profit']} margin={t['margin']}%")
