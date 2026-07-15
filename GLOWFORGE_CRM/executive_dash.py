"""Executive Dashboard — CEO 综合看板

健康评分 + 瀑布图 + 利润驱动 + AI 建议。
"""

import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ExecutiveDashboard:
    """CEO 仪表盘引擎"""

    def _import_db(self):
        sys.path.insert(0, BASE_DIR)
        import database as db_mod
        return db_mod

    def _get_pl_engine(self):
        try:
            sys.path.insert(0, BASE_DIR)
            from pl_engine import PLEngine
            return PLEngine()
        except Exception:
            return None

    def _get_invoice_engine(self):
        try:
            sys.path.insert(0, BASE_DIR)
            from invoice_engine import InvoiceEngine
            return InvoiceEngine()
        except Exception:
            return None

    def _get_expense_engine(self):
        try:
            sys.path.insert(0, BASE_DIR)
            from expense_engine import ExpenseEngine
            return ExpenseEngine()
        except Exception:
            return None

    def _get_budget_engine(self):
        try:
            sys.path.insert(0, BASE_DIR)
            from budget_engine import BudgetEngine
            return BudgetEngine()
        except Exception:
            return None

    def get_ceo_summary(self):
        """CEO 综合摘要"""
        db = self._import_db()
        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))
        conn.row_factory = sqlite3.Row

        # 总收入（本年度）
        year_start = f"{datetime.now().year}-01-01"
        revenue_row = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) as total FROM orders "
            "WHERE status NOT IN ('cancelled', 'lost') AND created_at >= ?",
            (year_start,)
        ).fetchone()
        total_revenue = float(revenue_row["total"])

        # 净利润（本年度）
        profit_row = conn.execute(
            "SELECT COALESCE(SUM(net_profit), 0) as total FROM orders "
            "WHERE status NOT IN ('cancelled', 'lost') AND created_at >= ?",
            (year_start,)
        ).fetchone()
        net_profit = float(profit_row["total"])

        # 上月收入（环比基准）
        import calendar
        now = datetime.now()
        first_this = now.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        first_last = last_month_end.replace(day=1)

        prev_rev = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) as total FROM orders "
            "WHERE status NOT IN ('cancelled', 'lost') AND created_at >= ? AND created_at < ?",
            (first_last.strftime("%Y-%m-%d"), first_this.strftime("%Y-%m-%d"))
        ).fetchone()
        prev_total = float(prev_rev["total"])
        rev_change = round(((total_revenue - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0

        # 总费用（本年度）
        expense_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM expenses "
            "WHERE status='approved' AND expense_date >= ?",
            (year_start,)
        ).fetchone()
        total_expenses = float(expense_row["total"])

        net_margin = round(net_profit / total_revenue * 100, 1) if total_revenue > 0 else 0
        expense_ratio = round(total_expenses / total_revenue * 100, 1) if total_revenue > 0 else 0

        # 当月收入
        curr_month_rev = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) as total FROM orders "
            "WHERE status NOT IN ('cancelled', 'lost') AND created_at >= ?",
            (first_this.strftime("%Y-%m-%d"),)
        ).fetchone()
        month_revenue = float(curr_month_rev["total"])

        # 发票状态
        inv_stats = conn.execute(
            "SELECT status, COUNT(*) as count FROM invoices GROUP BY status"
        ).fetchall()
        active_invoices = sum(r["count"] for r in inv_stats if r["status"] in ("draft", "sent"))
        overdue = sum(r["count"] for r in inv_stats if r["status"] == "overdue")

        # 预算预警数
        budget_alerts = 0
        try:
            be = self._get_budget_engine()
            if be:
                alerts = be.get_budget_alerts()
                budget_alerts = len(alerts)
        except Exception:
            pass

        # 现金流（简化）
        payments_in = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE payment_date >= ?",
            (year_start,)
        ).fetchone()
        cash_in = float(payments_in["total"])

        conn.close()
        cash_position = round(cash_in - total_expenses, 2)

        return {
            "total_revenue": round(total_revenue, 2),
            "net_profit": round(net_profit, 2),
            "net_margin": net_margin,
            "revenue_trend": rev_change,
            "month_revenue": round(month_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "expense_ratio": expense_ratio,
            "active_invoices": active_invoices,
            "overdue_count": overdue,
            "budget_alerts_count": budget_alerts,
            "cash_position": round(cash_position, 2),
        }

    def get_financial_health_score(self):
        """财务健康评分 (0-100)

        4 组件: profitability(25) + efficiency(25) + liquidity(25) + budget(25)
        """
        summary = self.get_ceo_summary()
        score = 0
        details = []

        # 1. 盈利能力 (25pts)
        net_margin = summary.get("net_margin", 0)
        if net_margin >= 20:
            profitability = 25
        elif net_margin >= 15:
            profitability = 20
        elif net_margin >= 10:
            profitability = 15
        elif net_margin >= 5:
            profitability = 10
        else:
            profitability = 5
        score += profitability
        details.append({
            "component": "profitability",
            "label": "盈利能力",
            "score": profitability,
            "max": 25,
            "detail": f"净利率 {net_margin}%",
        })

        # 2. 费用效率 (25pts)
        expense_ratio = summary.get("expense_ratio", 100)
        if expense_ratio <= 20:
            efficiency = 25
        elif expense_ratio <= 30:
            efficiency = 20
        elif expense_ratio <= 40:
            efficiency = 15
        elif expense_ratio <= 50:
            efficiency = 10
        else:
            efficiency = 5
        score += efficiency
        details.append({
            "component": "efficiency",
            "label": "费用效率",
            "score": efficiency,
            "max": 25,
            "detail": f"费用率 {expense_ratio}%",
        })

        # 3. 流动性/应收 (25pts)
        overdue = summary.get("overdue_count", 0)
        if overdue == 0:
            liquidity = 25
        elif overdue <= 2:
            liquidity = 20
        elif overdue <= 5:
            liquidity = 15
        elif overdue <= 10:
            liquidity = 10
        else:
            liquidity = 5
        score += liquidity
        details.append({
            "component": "liquidity",
            "label": "应收流动性",
            "score": liquidity,
            "max": 25,
            "detail": f"{overdue} 笔逾期发票",
        })

        # 4. 预算执行 (25pts)
        budget_alerts = summary.get("budget_alerts_count", 0)
        if budget_alerts == 0:
            budget = 25
        elif budget_alerts <= 2:
            budget = 20
        elif budget_alerts <= 5:
            budget = 15
        elif budget_alerts <= 10:
            budget = 10
        else:
            budget = 5
        score += budget
        details.append({
            "component": "budget",
            "label": "预算执行",
            "score": budget,
            "max": 25,
            "detail": f"{budget_alerts} 条超支预警",
        })

        # 等级
        if score >= 85:
            level = "excellent"
            label = "优秀"
        elif score >= 70:
            level = "good"
            label = "良好"
        elif score >= 50:
            level = "fair"
            label = "一般"
        else:
            level = "poor"
            label = "需改善"

        return {
            "total_score": score,
            "level": level,
            "label": label,
            "components": details,
            "max_score": 100,
        }

    def get_revenue_waterfall(self, period_id=None):
        """收入瀑布图

        Returns:
            list: [{label, value, type}] 用于 Chart.js waterfall
        """
        if period_id:
            try:
                pl = self._get_pl_engine()
                if pl:
                    pl_data = pl.generate_pl(period_id)
                    if "error" not in pl_data:
                        return [
                            {"label": "总收入", "value": pl_data["revenue"], "type": "total"},
                            {"label": "生产成本", "value": -pl_data["cogs"], "type": "negative"},
                            {"label": "毛利", "value": pl_data["gross_profit"], "type": "subtotal"},
                            {"label": "运营费用", "value": -pl_data["total_expenses"], "type": "negative"},
                            {"label": "净利润", "value": pl_data["net_profit"], "type": "total"},
                        ]
            except Exception:
                pass

        # 无 period_id：全年
        db = self._import_db()
        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))

        year_start = f"{datetime.now().year}-01-01"
        rev = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status NOT IN ('cancelled','lost') AND created_at >= ?",
            (year_start,)
        ).fetchone()[0]
        cogs = conn.execute(
            "SELECT COALESCE(SUM(production_cost),0) + COALESCE(SUM(shipping_cost),0) + COALESCE(SUM(platform_fee),0) "
            "FROM orders WHERE status NOT IN ('cancelled','lost') AND created_at >= ?",
            (year_start,)
        ).fetchone()[0]
        expenses = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE status='approved' AND expense_date >= ?",
            (year_start,)
        ).fetchone()[0]
        conn.close()

        rev_f = float(rev)
        cogs_f = float(cogs)
        exp_f = float(expenses)
        gross = rev_f - cogs_f
        net = gross - exp_f

        return [
            {"label": "总收入", "value": round(rev_f, 2), "type": "total"},
            {"label": "生产成本", "value": -round(cogs_f, 2), "type": "negative"},
            {"label": "毛利", "value": round(gross, 2), "type": "subtotal"},
            {"label": "运营费用", "value": -round(exp_f, 2), "type": "negative"},
            {"label": "净利润", "value": round(net, 2), "type": "total"},
        ]

    def get_profit_driver_analysis(self, period_id=None):
        """利润驱动因素分析"""
        try:
            pl = self._get_pl_engine()
            if pl:
                if period_id:
                    return pl.get_pl_by_dimension(period_id, "category")
                periods = pl.get_periods()
                if periods:
                    return pl.get_pl_by_dimension(periods[0]["id"], "category")
        except Exception:
            pass
        return []

    def get_cash_position(self):
        """现金流状况"""
        db = self._import_db()
        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))

        # 收款总额
        payments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments").fetchone()[0]

        # 已审批费用
        expenses = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE status='approved'"
        ).fetchone()[0]

        # 应收（已发/逾期发票）
        receivables = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status IN ('sent', 'overdue')"
        ).fetchone()[0]

        # 应付（未付款订单）
        payables = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status='pending_approval'"
        ).fetchone()[0]

        # 30天流入预测（近30天订单）
        forecast_in = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status NOT IN ('cancelled','lost') AND created_at >= datetime('now', '-30 days')"
        ).fetchone()[0]

        # 30天流出预测（近30天费用均值）
        monthly_expenses = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE status='approved' AND expense_date >= datetime('now', '-30 days')"
        ).fetchone()[0]

        conn.close()

        cash = float(payments) - float(expenses)
        forecast_out = float(monthly_expenses)
        net_position = float(forecast_in) - forecast_out

        return {
            "current_balance": round(cash, 2),
            "receivables": round(float(receivables), 2),
            "payables": round(float(payables), 2),
            "forecast_30day_inflow": round(float(forecast_in), 2),
            "forecast_30day_outflow": round(forecast_out, 2),
            "net_position": round(net_position, 2),
        }


# ==================== 测试 ====================
if __name__ == "__main__":
    d = ExecutiveDashboard()

    print("=== CEO Summary ===")
    s = d.get_ceo_summary()
    for k, v in s.items():
        print(f"  {k}: {v}")

    print("\n=== Financial Health Score ===")
    hs = d.get_financial_health_score()
    print(f"  Score: {hs['total_score']}/{hs['max_score']} ({hs['label']})")
    for c in hs["components"]:
        print(f"  {c['label']}: {c['score']}/{c['max']} — {c['detail']}")

    print("\n=== Revenue Waterfall ===")
    wf = d.get_revenue_waterfall()
    for item in wf:
        print(f"  {item['label']}: {item['value']} [{item['type']}]")

    print("\n=== Cash Position ===")
    cp = d.get_cash_position()
    for k, v in cp.items():
        print(f"  {k}: {v}")
