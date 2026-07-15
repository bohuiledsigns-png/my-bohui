"""Expense Tracker — 费用追踪

9 类费用分类 + 审批流 + 汇总。
"""

import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ExpenseEngine:
    """费用管理引擎"""

    CATEGORIES = [
        "operation", "marketing", "shipping", "commission",
        "salary", "office", "travel", "maintenance", "other",
    ]

    def _import_db(self):
        sys.path.insert(0, BASE_DIR)
        import database as db_mod
        return db_mod

    def add_expense(self, category, amount, currency="USD", expense_date=None,
                    vendor="", paid_by=None, notes="", receipt_path="", description=""):
        """添加费用"""
        if category not in self.CATEGORIES:
            return {"error": f"Invalid category: {category}"}
        if not expense_date:
            expense_date = datetime.now().strftime("%Y-%m-%d")

        db = self._import_db()
        eid = db.add_expense({
            "category": category,
            "amount": amount,
            "currency": currency,
            "expense_date": expense_date,
            "vendor": vendor,
            "description": description,
            "status": "pending",
            "paid_by": paid_by,
            "notes": notes,
            "receipt_path": receipt_path,
        })
        return {"id": eid, "status": "pending"}

    def get_expenses(self, category=None, status=None, start_date=None, end_date=None, limit=50):
        """获取费用列表"""
        db = self._import_db()
        return db.get_expenses(category, status, start_date, end_date, limit)

    def get_expenses_approved(self, start_date=None, end_date=None):
        """获取已审批费用（给 P&L Engine 用）"""
        db = self._import_db()
        return db.get_expenses(category=None, status="approved", start_date=start_date, end_date=end_date, limit=5000)

    def approve_expense(self, expense_id, approved_by):
        """审批通过"""
        db = self._import_db()
        expense = db.get_expense(expense_id)
        if not expense:
            return {"error": "Expense not found"}
        if expense["status"] != "pending":
            return {"error": f"Cannot approve expense with status '{expense['status']}'"}

        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))
        conn.execute(
            "UPDATE expenses SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
            (approved_by, expense_id)
        )
        conn.commit()
        conn.close()
        return {"status": "approved", "expense_id": expense_id}

    def reject_expense(self, expense_id, approved_by, reason=""):
        """驳回"""
        db = self._import_db()
        expense = db.get_expense(expense_id)
        if not expense:
            return {"error": "Expense not found"}
        if expense["status"] != "pending":
            return {"error": f"Cannot reject expense with status '{expense['status']}'"}

        import sqlite3
        conn = sqlite3.connect(os.path.join(BASE_DIR, "crm_data.db"))
        conn.execute(
            "UPDATE expenses SET status='rejected', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
            (approved_by, expense_id)
        )
        conn.commit()
        conn.close()
        return {"status": "rejected", "expense_id": expense_id}

    def get_expense_summary(self, group_by="category", start_date=None, end_date=None):
        """费用汇总"""
        db = self._import_db()
        return db.get_expense_summary(group_by, start_date, end_date)

    def get_expense_trend(self, months=6):
        """费用趋势"""
        db = self._import_db()
        return db.get_expense_trend(months)


# ==================== 测试 ====================
if __name__ == "__main__":
    e = ExpenseEngine()

    print("=== Add Expenses ===")
    for cat in ["marketing", "operation", "shipping"]:
        r = e.add_expense(cat, amount=500, currency="USD", vendor="Test Vendor",
                         notes=f"Test {cat} expense")
        print(f"  {cat}: {r}")

    print("\n=== All Expenses ===")
    expenses = e.get_expenses(limit=10)
    for exp in expenses:
        print(f"  {exp['category']}: ${exp['amount']} [{exp['status']}] {exp.get('vendor','')}")

    if expenses:
        eid = expenses[0]["id"]
        print(f"\n=== Approve Expense #{eid} ===")
        r = e.approve_expense(eid, approved_by=1)
        print(f"  {r}")

    print("\n=== Summary by Category ===")
    summary = e.get_expense_summary()
    for s in summary:
        print(f"  {s['category']}: ${s['total']} ({s['count']} expenses)")

    print("\n=== Trend ===")
    trend = e.get_expense_trend(6)
    for t in trend:
        print(f"  {t['month']}: ${t['total']}")
