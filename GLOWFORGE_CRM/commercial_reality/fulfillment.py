"""FulfillmentTracker — 订单履约追踪器

订单生成后的"现实世界"追踪层：
  生产 → 质检 → 发货 → 交期偏差监控 → 超期告警

不改动 orders 表，所有状态通过 order_id 外键关联。
"""
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta

logger = logging.getLogger("glowforge.commercial_reality.fulfillment")

# ── 状态常量 ──
PRODUCTION_PENDING = "PENDING"
PRODUCTION_SCHEDULED = "SCHEDULED"
PRODUCTION_IN_PROGRESS = "IN_PROGRESS"
PRODUCTION_COMPLETED = "COMPLETED"
PRODUCTION_CANCELLED = "CANCELLED"

QC_PENDING = "PENDING"
QC_PASSED = "PASSED"
QC_FAILED = "FAILED"
QC_NOT_REQUIRED = "NOT_REQUIRED"

SHIPMENT_PENDING = "PENDING"
SHIPMENT_BOOKED = "BOOKED"
SHIPMENT_SHIPPED = "SHIPPED"
SHIPMENT_DELIVERED = "DELIVERED"
SHIPMENT_CANCELLED = "CANCELLED"

PAYMENT_PENDING = "PENDING"
PAYMENT_DEPOSIT = "DEPOSIT_PAID"
PAYMENT_FULL = "FULL_PAID"
PAYMENT_REFUNDING = "REFUNDING"
PAYMENT_DISPUTED = "DISPUTED"

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"


class FulfillmentTracker:
    """订单履约追踪器

    用法:
        tracker = FulfillmentTracker(db_path)
        tracker.create_fulfillment(order_id=42, promised_delivery_date="2026-07-20")
        tracker.update_production(42, "IN_PROGRESS")
        print(tracker.check_overdue())
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── 创建 ──

    def create_fulfillment(self, order_id: int,
                           promised_delivery_date: str = "",
                           amount: float = 0,
                           currency: str = "USD") -> bool:
        """订单生成时调用，创建履约追踪记录 + 资金初始记录。

        幂等设计：同一 order_id 已存在则跳过。
        """
        try:
            conn = self._get_conn()
            try:
                # 检查是否已存在
                existing = conn.execute(
                    "SELECT id FROM order_fulfillment WHERE order_id=?",
                    (order_id,),
                ).fetchone()
                if existing:
                    return True  # 已存在，幂等

                # 生成 fulfillment_id
                seq = conn.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM order_fulfillment"
                ).fetchone()[0]
                fid = f"FUL-{datetime.now().strftime('%Y%m%d')}-{seq:04d}"

                conn.execute(
                    """INSERT INTO order_fulfillment
                       (order_id, fulfillment_id, promised_delivery_date)
                       VALUES (?, ?, ?)""",
                    (order_id, fid, promised_delivery_date),
                )
                conn.commit()
                logger.info("[Fulfillment] Created %s for order %d", fid, order_id)
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] create failed order=%d: %s", order_id, e)
            return False

    # ── 状态更新 ──

    def update_production(self, order_id: int, status: str,
                          note: str = "") -> bool:
        """更新生产状态"""
        return self._update_field(order_id, "production_status", status,
                                  valid=(
                                      PRODUCTION_PENDING,
                                      PRODUCTION_SCHEDULED,
                                      PRODUCTION_IN_PROGRESS,
                                      PRODUCTION_COMPLETED,
                                      PRODUCTION_CANCELLED,
                                  ), note=note)

    def update_qc(self, order_id: int, status: str,
                   note: str = "") -> bool:
        """更新质检状态"""
        return self._update_field(order_id, "qc_status", status,
                                  valid=(QC_PENDING, QC_PASSED, QC_FAILED, QC_NOT_REQUIRED),
                                  note=note)

    def update_shipment(self, order_id: int, status: str,
                         tracking_no: str = "",
                         actual_delivery_date: str = "") -> bool:
        """更新发货状态"""
        try:
            conn = self._get_conn()
            try:
                parts = ["shipment_status=?", "updated_at=CURRENT_TIMESTAMP"]
                vals = [status]
                if tracking_no:
                    parts.append("internal_note=CASE WHEN internal_note='' THEN ? ELSE internal_note || ' | ' || ? END")
                    vals.extend([f"跟踪号: {tracking_no}"] * 2)
                if actual_delivery_date:
                    parts.append("actual_delivery_date=?")
                    vals.append(actual_delivery_date)
                vals.append(order_id)

                conn.execute(
                    f"UPDATE order_fulfillment SET {', '.join(parts)} WHERE order_id=?",
                    vals,
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] update_shipment failed order=%d: %s", order_id, e)
            return False

    def update_payment(self, order_id: int, status: str) -> bool:
        """更新付款状态"""
        return self._update_field(order_id, "payment_status", status,
                                  valid=(
                                      PAYMENT_PENDING,
                                      PAYMENT_DEPOSIT,
                                      PAYMENT_FULL,
                                      PAYMENT_REFUNDING,
                                      PAYMENT_DISPUTED,
                                  ))

    def _update_field(self, order_id: int, field: str, value: str,
                      valid: tuple = (), note: str = "") -> bool:
        """通用字段更新 + 校验 + 内部备注追加"""
        if valid and value not in valid:
            logger.warning("[Fulfillment] Invalid %s=%s for order %d", field, value, order_id)
            return False
        try:
            conn = self._get_conn()
            try:
                if note:
                    conn.execute(
                        f"""UPDATE order_fulfillment
                            SET {field}=?, internal_note=CASE
                                WHEN internal_note='' THEN ?
                                ELSE internal_note || ' | ' || ?
                            END, updated_at=CURRENT_TIMESTAMP
                            WHERE order_id=?""",
                        (value, note, note, order_id),
                    )
                else:
                    conn.execute(
                        f"UPDATE order_fulfillment SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE order_id=?",
                        (value, order_id),
                    )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] update %s failed order=%d: %s", field, order_id, e)
            return False

    # ── 风险控制 ──

    def set_risk(self, order_id: int, level: str, reason: str = "") -> bool:
        """设置风险等级，自动追加 internal_note。"""
        if level not in (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL):
            return False
        try:
            conn = self._get_conn()
            try:
                note_part = f"风险{level}: {reason}" if reason else f"风险{level}"
                conn.execute(
                    """UPDATE order_fulfillment
                       SET risk_level=?, internal_note=CASE
                           WHEN internal_note='' THEN ?
                           ELSE internal_note || ' | ' || ?
                       END, updated_at=CURRENT_TIMESTAMP
                       WHERE order_id=?""",
                    (level, note_part, note_part, order_id),
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] set_risk failed order=%d: %s", order_id, e)
            return False

    def mark_unfulfillable(self, order_id: int, reason: str) -> bool:
        """标记为无法履约（is_fulfillable=0）+ 风险 CRITICAL。

        触发此方法后，系统应：
        - 暂停对该客户的所有主动营销
        - 生成 escalation 任务推给老板
        """
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE order_fulfillment
                       SET is_fulfillable=0, risk_level='CRITICAL',
                           internal_note=CASE
                               WHEN internal_note='' THEN ?
                               ELSE internal_note || ' | ' || ?
                           END,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE order_id=?""",
                    (f"无法履约: {reason}", f"无法履约: {reason}", order_id),
                )
                conn.commit()
                logger.warning("[Fulfillment] Order %d marked UNFULFILLABLE: %s", order_id, reason)
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] mark_unfulfillable failed order=%d: %s", order_id, e)
            return False

    # ── 查询 ──

    def get_fulfillment(self, order_id: int) -> dict | None:
        """获取某订单的完整履约信息"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM order_fulfillment WHERE order_id=?",
                    (order_id,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] get failed order=%d: %s", order_id, e)
            return None

    def get_all_fulfillments(self, limit: int = 50) -> list:
        """获取所有履约记录（最近优先）"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM order_fulfillment ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] list failed: %s", e)
            return []

    def get_active_tasks(self) -> list[dict]:
        """获取所有需要关注的活跃任务（联合 orders + customers 表）

        返回每个履约记录附带：
          - order_no, customer_name, customer_company, total_amount, currency
          - 来自 fulfillment 表的所有字段

        按风险等级排序：CRITICAL > HIGH > MEDIUM > LOW
        """
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT
                           f.*,
                           o.order_no,
                           o.total_amount,
                           o.currency,
                           c.name AS customer_name,
                           c.company AS customer_company,
                           c.whatsapp AS customer_whatsapp
                       FROM order_fulfillment f
                       LEFT JOIN orders o ON f.order_id = o.id
                       LEFT JOIN customers c ON o.customer_id = c.id
                       ORDER BY
                           CASE f.risk_level
                               WHEN 'CRITICAL' THEN 0
                               WHEN 'HIGH' THEN 1
                               WHEN 'MEDIUM' THEN 2
                               ELSE 3
                           END ASC,
                           f.promised_delivery_date ASC
                       LIMIT 100""",
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] get_active_tasks failed: %s", e)
            return []

    # ── 超期监控 ──

    def check_overdue(self) -> list[dict]:
        """检查所有即将/已经超期的订单。

        扫描逻辑：
        - 已交付的跳过
        - promised_delivery_date 非空的检查
        - 超期 0 天 → RISK_MEDIUM（今日到期）
        - 超期 1-3 天 → RISK_HIGH
        - 超期 >3 天 → RISK_CRITICAL（自动告警标记）
        - 距到期 <3 天 → RISK_MEDIUM（即将到期）

        Returns:
            list[dict]: 每个元素包含 order_id, promised_date, risk, days_overdue
        """
        results = []
        try:
            conn = self._get_conn()
            try:
                today = datetime.now().date()
                rows = conn.execute(
                    """SELECT * FROM order_fulfillment
                       WHERE promised_delivery_date != ''
                         AND shipment_status NOT IN ('DELIVERED','CANCELLED')
                         AND is_fulfillable = 1
                       ORDER BY promised_delivery_date ASC""",
                ).fetchall()

                for r in rows:
                    d = dict(r)
                    try:
                        promised = datetime.strptime(d["promised_delivery_date"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        continue

                    delta = (today - promised).days

                    if delta > 3:
                        new_risk = RISK_CRITICAL
                    elif delta > 0:
                        new_risk = RISK_HIGH
                    elif delta == 0:
                        new_risk = RISK_MEDIUM
                    elif delta >= -3:
                        new_risk = RISK_MEDIUM  # 即将到期
                    else:
                        continue  # 还很早，跳过

                    # 只在风险升高时更新 DB
                    risk_order = {RISK_LOW: 0, RISK_MEDIUM: 1, RISK_HIGH: 2, RISK_CRITICAL: 3}
                    if risk_order.get(new_risk, 0) > risk_order.get(d["risk_level"], 0):
                        conn.execute(
                            "UPDATE order_fulfillment SET risk_level=?, updated_at=CURRENT_TIMESTAMP WHERE order_id=?",
                            (new_risk, d["order_id"]),
                        )

                    results.append({
                        "order_id": d["order_id"],
                        "fulfillment_id": d["fulfillment_id"],
                        "promised_delivery_date": d["promised_delivery_date"],
                        "risk_level": new_risk,
                        "days_overdue": delta,
                        "production_status": d["production_status"],
                        "qc_status": d["qc_status"],
                        "shipment_status": d["shipment_status"],
                        "payment_status": d["payment_status"],
                    })

                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] check_overdue failed: %s", e)

        return results

    # ── 仪表盘 ──

    def get_dashboard(self) -> dict:
        """聚合履约仪表盘数据"""
        try:
            conn = self._get_conn()
            try:
                total = conn.execute("SELECT COUNT(*) FROM order_fulfillment").fetchone()[0]
                by_risk = dict(conn.execute(
                    "SELECT risk_level, COUNT(*) FROM order_fulfillment GROUP BY risk_level"
                ).fetchall())
                by_prod = dict(conn.execute(
                    "SELECT production_status, COUNT(*) FROM order_fulfillment GROUP BY production_status"
                ).fetchall())
                by_ship = dict(conn.execute(
                    "SELECT shipment_status, COUNT(*) FROM order_fulfillment GROUP BY shipment_status"
                ).fetchall())
                unfulfillable = conn.execute(
                    "SELECT COUNT(*) FROM order_fulfillment WHERE is_fulfillable=0"
                ).fetchone()[0]
                overdue = conn.execute(
                    """SELECT COUNT(*) FROM order_fulfillment
                       WHERE promised_delivery_date != ''
                         AND shipment_status NOT IN ('DELIVERED','CANCELLED')
                         AND date(promised_delivery_date) < date('now')"""
                ).fetchone()[0]

                return {
                    "total_fulfillments": total,
                    "by_risk": {
                        "low": by_risk.get("LOW", 0),
                        "medium": by_risk.get("MEDIUM", 0),
                        "high": by_risk.get("HIGH", 0),
                        "critical": by_risk.get("CRITICAL", 0),
                    },
                    "by_production": {
                        "pending": by_prod.get("PENDING", 0),
                        "scheduled": by_prod.get("SCHEDULED", 0),
                        "in_progress": by_prod.get("IN_PROGRESS", 0),
                        "completed": by_prod.get("COMPLETED", 0),
                    },
                    "by_shipment": {
                        "pending": by_ship.get("PENDING", 0),
                        "shipped": by_ship.get("SHIPPED", 0),
                        "delivered": by_ship.get("DELIVERED", 0),
                    },
                    "unfulfillable": unfulfillable,
                    "overdue_count": overdue,
                    "checked_at": datetime.now().isoformat(),
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Fulfillment] get_dashboard failed: %s", e)
            return {"error": str(e)}
