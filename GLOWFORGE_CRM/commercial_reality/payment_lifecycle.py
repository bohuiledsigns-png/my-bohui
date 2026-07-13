"""PaymentLifecycle — 资金生命周期管理器

状态机:
  INTENT → COMMITMENT → DEPOSIT_PAID → FULL_PAID → CLOSED
                        ↘             ↘
                        REFUNDING     DISPUTED
                        → CLOSED      → CLOSED

不改动 orders/payments 表，所有状态通过 order_id 关联。
"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger("glowforge.commercial_reality.payment")

# ── 阶段常量 ──
STAGE_INTENT = "INTENT"              # 客户表示购买意向
STAGE_COMMITMENT = "COMMITMENT"      # 已下单（PI发出）
STAGE_DEPOSIT = "DEPOSIT_PAID"       # 定金已收
STAGE_FULL = "FULL_PAID"             # 尾款已收
STAGE_REFUNDING = "REFUNDING"        # 退款中
STAGE_DISPUTED = "DISPUTED"          # 纠纷中
STAGE_CLOSED = "CLOSED"              # 终态

# 合法状态转换
_VALID_TRANSITIONS = {
    STAGE_INTENT:      [STAGE_COMMITMENT],
    STAGE_COMMITMENT:  [STAGE_DEPOSIT, STAGE_CLOSED],          # 客户取消 → CLOSED
    STAGE_DEPOSIT:     [STAGE_FULL, STAGE_REFUNDING, STAGE_DISPUTED],
    STAGE_FULL:        [STAGE_REFUNDING, STAGE_DISPUTED, STAGE_CLOSED],
    STAGE_REFUNDING:   [STAGE_CLOSED],
    STAGE_DISPUTED:    [STAGE_FULL, STAGE_REFUNDING, STAGE_CLOSED],
    STAGE_CLOSED:      [],  # 终态
}


class PaymentLifecycle:
    """资金生命周期管理器

    用法:
        pm = PaymentLifecycle(db_path)
        pm.create_payment(order_id=42, amount=5000)
        pm.update_stage(42, "DEPOSIT_PAID", {"paid_at": "...", "payer": "..."})
        print(pm.check_overdue_deposits())
        print(pm.check_overdue_balances())
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── 创建 ──

    def create_payment(self, order_id: int, amount: float,
                       currency: str = "USD",
                       stage: str = STAGE_COMMITMENT) -> bool:
        """订单生成时调用，创建资金生命周期记录。

        幂等设计：同一 order_id 已存在则跳过。
        """
        if stage not in (STAGE_INTENT, STAGE_COMMITMENT):
            stage = STAGE_COMMITMENT
        try:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT id FROM payment_lifecycle WHERE order_id=?",
                    (order_id,),
                ).fetchone()
                if existing:
                    return True

                seq = conn.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM payment_lifecycle"
                ).fetchone()[0]
                pid = f"PAY-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"

                conn.execute(
                    """INSERT INTO payment_lifecycle
                       (order_id, payment_id, stage, amount, currency)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, pid, stage, amount, currency),
                )
                conn.commit()
                logger.info("[PaymentLifecycle] Created %s for order %d (%.2f %s)",
                            pid, order_id, amount, currency)
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] create failed order=%d: %s", order_id, e)
            return False

    # ── 状态更新 ──

    def update_stage(self, order_id: int, stage: str,
                     detail: dict | None = None) -> bool:
        """更新资金阶段，自动检查状态转换合法性。

        detail 支持的字段:
          - paid_at:      收款时间（ISO 字符串）
          - payer_name:   付款人名称
          - transaction_ref: 银行水单/交易参考号
          - payment_link:  付款链接
          - refund_amount: 退款金额
          - refund_reason: 退款原因
          - dispute_status: 纠纷状态 (OPEN / RESOLVED / CLOSED)
          - payment_method: 付款方式 (T/T / PayPal / 连连)
        """
        if stage not in _VALID_TRANSITIONS:
            logger.warning("[PaymentLifecycle] Invalid stage: %s", stage)
            return False

        detail = detail or {}

        try:
            conn = self._get_conn()
            try:
                # 读取当前阶段，检查转换合法性
                row = conn.execute(
                    "SELECT stage, payment_id FROM payment_lifecycle WHERE order_id=?",
                    (order_id,),
                ).fetchone()
                if not row:
                    logger.warning("[PaymentLifecycle] No record for order %d", order_id)
                    return False

                current = row["stage"]
                if stage != current and stage not in _VALID_TRANSITIONS.get(current, []):
                    logger.warning(
                        "[PaymentLifecycle] Illegal transition %s → %s for order %d",
                        current, stage, order_id,
                    )
                    return False

                # 构建更新字段
                sets = ["stage=?", "updated_at=CURRENT_TIMESTAMP"]
                vals = [stage]

                if "paid_at" in detail:
                    sets.append("paid_at=?")
                    vals.append(detail["paid_at"])
                if "payer_name" in detail:
                    sets.append("payer_name=?")
                    vals.append(detail["payer_name"])
                if "transaction_ref" in detail:
                    sets.append("transaction_ref=?")
                    vals.append(detail["transaction_ref"])
                if "payment_method" in detail:
                    sets.append("payment_method=?")
                    vals.append(detail["payment_method"])
                if "payment_link" in detail:
                    sets.append("payment_link=?")
                    vals.append(detail["payment_link"])
                if "refund_amount" in detail:
                    sets.append("refund_amount=?")
                    vals.append(float(detail["refund_amount"]))
                if "refund_reason" in detail:
                    sets.append("refund_reason=?")
                    vals.append(detail["refund_reason"])
                if "dispute_status" in detail:
                    sets.append("dispute_status=?")
                    vals.append(detail["dispute_status"])

                vals.append(order_id)
                conn.execute(
                    f"UPDATE payment_lifecycle SET {', '.join(sets)} WHERE order_id=?",
                    vals,
                )
                conn.commit()

                logger.info("[PaymentLifecycle] Order %d: %s → %s", order_id, current, stage)
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] update_stage failed order=%d: %s", order_id, e)
            return False

    # ── 查询 ──

    def get_payment(self, order_id: int) -> dict | None:
        """获取某订单的资金生命周期记录"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM payment_lifecycle WHERE order_id=?",
                    (order_id,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] get failed order=%d: %s", order_id, e)
            return None

    def list_payments(self, limit: int = 50) -> list:
        """获取所有资金记录（最近优先）"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM payment_lifecycle ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] list failed: %s", e)
            return []

    # ── 逾期监控 ──

    def check_overdue_deposits(self, grace_days: int = 3) -> list[dict]:
        """检查订单生成后超过 grace_days 未付定金的订单。

        Returns:
            list[dict]: 逾期订金订单列表
        """
        try:
            conn = self._get_conn()
            try:
                cutoff = (datetime.now() - timedelta(days=grace_days)).isoformat()
                rows = conn.execute(
                    """SELECT pl.*, o.order_no, c.name as customer_name
                       FROM payment_lifecycle pl
                       LEFT JOIN orders o ON pl.order_id = o.id
                       LEFT JOIN customers c ON o.customer_id = c.id
                       WHERE pl.stage IN ('INTENT','COMMITMENT')
                         AND pl.created_at < ?
                       ORDER BY pl.created_at ASC""",
                    (cutoff,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] check_overdue_deposits failed: %s", e)
            return []

    def check_overdue_balances(self, grace_days: int = 7) -> list[dict]:
        """检查付了定金但超过 grace_days 未付尾款的订单。

        Returns:
            list[dict]: 尾款逾期订单列表
        """
        try:
            conn = self._get_conn()
            try:
                cutoff = (datetime.now() - timedelta(days=grace_days)).isoformat()
                rows = conn.execute(
                    """SELECT pl.*, o.order_no, c.name as customer_name
                       FROM payment_lifecycle pl
                       LEFT JOIN orders o ON pl.order_id = o.id
                       LEFT JOIN customers c ON o.customer_id = c.id
                       WHERE pl.stage = 'DEPOSIT_PAID'
                         AND pl.paid_at < ?
                       ORDER BY pl.paid_at ASC""",
                    (cutoff,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] check_overdue_balances failed: %s", e)
            return []

    def check_active_disputes(self) -> list[dict]:
        """检查所有活跃纠纷"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT pl.*, o.order_no, c.name as customer_name
                       FROM payment_lifecycle pl
                       LEFT JOIN orders o ON pl.order_id = o.id
                       LEFT JOIN customers c ON o.customer_id = c.id
                       WHERE pl.stage = 'DISPUTED'
                          OR (pl.stage = 'REFUNDING' AND pl.dispute_status IN ('','OPEN'))
                       ORDER BY pl.updated_at DESC""",
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] check_active_disputes failed: %s", e)
            return []

    # ── 仪表盘 ──

    def get_dashboard(self) -> dict:
        """聚合资金仪表盘数据"""
        try:
            conn = self._get_conn()
            try:
                total = conn.execute("SELECT COUNT(*) FROM payment_lifecycle").fetchone()[0]
                by_stage = dict(conn.execute(
                    "SELECT stage, COUNT(*) FROM payment_lifecycle GROUP BY stage"
                ).fetchall())
                total_amount = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM payment_lifecycle"
                ).fetchone()[0]
                paid_amount = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM payment_lifecycle WHERE stage IN ('DEPOSIT_PAID','FULL_PAID','CLOSED')"
                ).fetchone()[0]
                refund_total = conn.execute(
                    "SELECT COALESCE(SUM(refund_amount), 0) FROM payment_lifecycle"
                ).fetchone()[0]
                dispute_count = conn.execute(
                    "SELECT COUNT(*) FROM payment_lifecycle WHERE stage IN ('DISPUTED','REFUNDING')"
                ).fetchone()[0]

                return {
                    "total_payments": total,
                    "by_stage": {
                        "intent": by_stage.get("INTENT", 0),
                        "commitment": by_stage.get("COMMITMENT", 0),
                        "deposit_paid": by_stage.get("DEPOSIT_PAID", 0),
                        "full_paid": by_stage.get("FULL_PAID", 0),
                        "refunding": by_stage.get("REFUNDING", 0),
                        "disputed": by_stage.get("DISPUTED", 0),
                        "closed": by_stage.get("CLOSED", 0),
                    },
                    "total_amount": total_amount,
                    "paid_amount": paid_amount,
                    "outstanding": total_amount - paid_amount,
                    "refund_total": refund_total,
                    "active_disputes": dispute_count,
                    "checked_at": datetime.now().isoformat(),
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error("[PaymentLifecycle] get_dashboard failed: %s", e)
            return {"error": str(e)}
