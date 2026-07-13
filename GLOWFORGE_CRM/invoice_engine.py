"""Invoice Manager — 发票管理

自动编号 INV-YYYYMM-NNNNN、生命周期追踪、逾期提醒。
"""

import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class InvoiceEngine:
    """发票管理引擎"""

    def _import_db(self):
        sys.path.insert(0, BASE_DIR)
        import database as db_mod
        return db_mod

    def _next_invoice_no(self):
        """生成发票号: INV-202606-00001"""
        now = datetime.now()
        prefix = f"INV-{now.strftime('%Y%m')}-"
        db = self._import_db()
        last = db.get_invoices(status=None, limit=1)
        if last:
            import re
            nums = [int(re.search(r'(\d+)$', inv.get("invoice_no", "00000")).group(1)) for inv in last if re.search(r'(\d+)$', inv.get("invoice_no", ""))]
            max_num = max(nums) if nums else 0
        else:
            max_num = 0
        return f"{prefix}{max_num + 1:05d}"

    def create_invoice(self, order_id, created_by=None):
        """从订单创建发票"""
        sys.path.insert(0, BASE_DIR)
        from database import get_order, add_invoice, update_order

        order = get_order(order_id)
        if not order:
            return {"error": "Order not found"}

        now = datetime.now()
        due = now + timedelta(days=30)

        invoice_no = self._next_invoice_no()
        iid = add_invoice({
            "invoice_no": invoice_no,
            "order_id": order_id,
            "customer_id": order.get("customer_id"),
            "issue_date": now.strftime("%Y-%m-%d"),
            "due_date": due.strftime("%Y-%m-%d"),
            "total_amount": float(order.get("total_amount", 0)),
            "currency": order.get("currency", "USD"),
            "status": "draft",
            "notes": "",
            "created_by": created_by,
        })

        # 回写 orders.invoice_id
        update_order(order_id, {"invoice_id": iid})

        return {"id": iid, "invoice_no": invoice_no, "status": "draft"}

    def get_invoices(self, status=None, limit=50):
        """获取发票列表"""
        db = self._import_db()
        return db.get_invoices(status, limit)

    def get_invoice(self, invoice_id):
        """获取发票详情"""
        db = self._import_db()
        return db.get_invoice(invoice_id)

    def send_invoice(self, invoice_id):
        """标记为已发送"""
        db = self._import_db()
        invoice = db.get_invoice(invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}
        if invoice["status"] != "draft":
            return {"error": f"Cannot send invoice with status '{invoice['status']}'"}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.update_invoice(invoice_id, status="sent", sent_at=now)
        return {"status": "sent", "invoice_id": invoice_id}

    def mark_paid(self, invoice_id, payment_id=None):
        """标记为已付款"""
        db = self._import_db()
        invoice = db.get_invoice(invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}
        if invoice["status"] in ("paid", "cancelled"):
            return {"error": f"Cannot pay invoice with status '{invoice['status']}'"}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.update_invoice(invoice_id, status="paid", paid_at=now)

        # 如果提供了 payment_id、回写 payments.invoice_id
        if payment_id:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE payments SET invoice_id=? WHERE id=?", (invoice_id, payment_id))
            conn.commit()
            conn.close()

        return {"status": "paid", "invoice_id": invoice_id}

    def cancel_invoice(self, invoice_id):
        """取消发票"""
        db = self._import_db()
        invoice = db.get_invoice(invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}
        if invoice["status"] == "paid":
            return {"error": "Cannot cancel a paid invoice"}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.update_invoice(invoice_id, status="cancelled", cancelled_at=now)
        return {"status": "cancelled", "invoice_id": invoice_id}

    def get_overdue_invoices(self):
        """获取逾期发票"""
        db = self._import_db()
        return db.get_overdue_invoices()

    def get_invoice_stats(self):
        """发票统计"""
        db = self._import_db()
        return db.get_invoice_stats()

    def check_and_update_overdue(self):
        """检查并更新逾期状态"""
        db = self._import_db()
        overdue = db.get_overdue_invoices()
        count = 0
        for inv in overdue:
            if inv["status"] == "sent":
                db.update_invoice(inv["id"], status="overdue")
                count += 1
        return {"updated": count}


# ==================== 测试 ====================
if __name__ == "__main__":
    eng = InvoiceEngine()

    print("=== Invoice Stats ===")
    stats = eng.get_invoice_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n=== Overdue Invoices ===")
    overdue = eng.get_overdue_invoices()
    for inv in overdue:
        print(f"  {inv.get('invoice_no','?')}: {inv.get('customer_name','?')} due={inv.get('due_date','?')}")
    if not overdue:
        print("  (none)")

    print("\n=== Create Invoice from Order #1 ===")
    r = eng.create_invoice(1)
    print(f"  {r}")

    print("\n=== All Invoices ===")
    invoices = eng.get_invoices(limit=10)
    for inv in invoices:
        print(f"  {inv['invoice_no']}: {inv.get('customer_name','?')} ${inv['total_amount']} [{inv['status']}] due={inv.get('due_date','?')}")
