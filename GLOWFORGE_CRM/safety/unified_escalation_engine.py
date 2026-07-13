"""UEE — Unified Escalation Engine

System Control Plane 核心。
汇总 4 类 escalation（PAYMENT / EXECUTION / SLA / SYSTEM）到统一队列，
提供 severity scoring、auto-assignment、action APIs。

使用方式:
    from safety.unified_escalation_engine import UnifiedEscalationEngine
    uee = UnifiedEscalationEngine()
    uee.scan_all()  # 全量扫描 4 类源，写入 unified_escalations 表
"""

import time
import json
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger("UEE")

# ==================== Severity Constants ====================

# 年龄分钟 → 基础 severity 映射
AGE_SEVERITY = [
    (0, 0.1),       # < 30min → 0.1
    (30, 0.3),      # 30min+  → 0.3
    (60, 0.4),      # 1h+     → 0.4
    (180, 0.5),     # 3h+     → 0.5
    (360, 0.6),     # 6h+     → 0.6
    (720, 0.7),     # 12h+    → 0.7
    (1440, 0.8),    # 24h+    → 0.8
    (2880, 0.9),    # 48h+    → 0.9
    (4320, 0.95),   # 72h+    → 0.95
]

# 金额阈值 → 金额因子
AMOUNT_SEVERITY = [
    (0, 0.0),
    (500, 0.1),
    (1000, 0.2),
    (3000, 0.3),
    (5000, 0.4),
    (10000, 0.5),
    (20000, 0.6),
    (50000, 0.8),
]

SEVERITY_LABELS = [
    (0.0, "low"),
    (0.3, "medium"),
    (0.5, "high"),
    (0.7, "critical"),
]


def _age_to_base_severity(age_minutes):
    """年龄分钟 → 基础 severity"""
    for threshold, sev in reversed(AGE_SEVERITY):
        if age_minutes >= threshold:
            return sev
    return 0.1


def _amount_to_factor(amount):
    """金额 → 乘数因子 (1.0–2.0)"""
    for threshold, factor in reversed(AMOUNT_SEVERITY):
        if amount >= threshold:
            return 1.0 + factor
    return 1.0


def _severity_label(score):
    """连续分数 → 等级标签"""
    for threshold, label in reversed(SEVERITY_LABELS):
        if score >= threshold:
            return label
    return "low"


def _sla_risk_factor(sla_deadline):
    """SLA 截止时间 → 风险乘数（越近越高）"""
    if not sla_deadline:
        return 1.0
    try:
        deadline = datetime.strptime(str(sla_deadline)[:19], "%Y-%m-%d %H:%M:%S")
        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            return 1.8  # 已超时
        if remaining <= 900:
            return 1.5  # 15min 内
        if remaining <= 3600:
            return 1.3  # 1h 内
        return 1.0
    except Exception:
        return 1.0


def _escalation_level_factor(level):
    """escalation level → 乘数"""
    return 1.0 + (level or 0) * 0.2  # 每级 +20%


class UnifiedEscalationEngine:
    """统一升级引擎

    职责:
        1. scan_all() — 全量扫描 4 类源 → 标准化事件
        2. calculate_severity() — 连续 severity 评分
        3. auto_assign() — 规则分配 owner
        4. 输出到 unified_escalations 表
    """

    def __init__(self, db=None):
        self._db = db

    # ==================== Main Entry Point ====================

    def scan_all(self):
        """全量扫描所有来源，返回新创建的 escalation 数量"""
        total = 0
        for scanner in [
            self._scan_payment,
            self._scan_execution,
            self._scan_sla,
            self._scan_system,
        ]:
            try:
                events = scanner()
                for ev in events:
                    ev["severity"] = self.calculate_severity(ev)
                    ev["severity_label"] = _severity_label(ev["severity"])
                    ev["owner"] = self.auto_assign(ev)
                    try:
                        from database import add_unified_escalation
                        eid = add_unified_escalation(ev)
                        if eid:
                            total += 1
                    except Exception as e:
                        logger.error(f"UEE insert error: {e}")
            except Exception as e:
                logger.error(f"UEE scanner {scanner.__name__} error: {e}")
        return total

    # ==================== Severity Scoring ====================

    def calculate_severity(self, event):
        """6 维 severity 评分，连续值 0.0–1.0

        维度:
            1. age — 事件年龄
            2. amount — 涉及金额
            3. sla — SLA 紧迫度
            4. escalation_level — 已升级次数
            5. customer_value — 客户价值（预留）
            6. type_weight — 事件类型权重
        """
        age = event.get("age_minutes", 0)
        ctx = event.get("context", {})

        # 1. 年龄基础分
        base = _age_to_base_severity(age)

        # 2. 金额修正
        amount = float(ctx.get("amount", 0) or 0)
        amount_factor = _amount_to_factor(amount)

        # 3. SLA 修正
        sla_factor = _sla_risk_factor(event.get("sla_deadline", ""))

        # 4. escalation level 修正
        level_factor = _escalation_level_factor(event.get("escalation_level", 0))

        # 5. 类型权重
        type_weights = {
            "PAYMENT": 1.1,
            "EXECUTION": 1.0,
            "SLA": 0.9,
            "SYSTEM": 0.8,
        }
        type_factor = type_weights.get(event.get("escalation_type", ""), 1.0)

        # 6. 合成
        score = base * amount_factor * sla_factor * level_factor * type_factor
        return min(max(score, 0.0), 1.0)

    # ==================== Auto Assignment ====================

    def auto_assign(self, event):
        """基于类型 + severity 的规则分配"""
        etype = event.get("escalation_type", "")
        source = event.get("escalation_source", "")
        sev = event.get("severity", 0.5)

        # PAYMENT: 资金相关 → finance
        if etype == "PAYMENT":
            if sev >= 0.7:
                return "finance_manager"
            return "finance_staff"

        # EXECUTION: 执行阻塞 → production
        if etype == "EXECUTION":
            if source in ("production_stuck", "shipping_delay"):
                return "production_manager"
            return "production_staff"

        # SLA: 时间风险 → sales
        if etype == "SLA":
            if sev >= 0.7:
                return "sales_manager"
            return "sales_staff"

        # SYSTEM: 系统异常 → admin
        if etype == "SYSTEM":
            return "system_admin"

        return "unassigned"

    # ==================== PAYMENT Scanner ====================

    def _scan_payment(self):
        """扫描资金风险事件"""
        events = []
        try:
            from database import get_db

            conn = get_db()

            # 1. 已发银行信息但未确认付款 >30min
            rows = conn.execute(
                """SELECT o.*, c.name as customer_name
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id=c.id
                   WHERE o.status='waiting_deposit'
                     AND o.deposit_status='bank_sent'
                     AND (julianday('now') - julianday(COALESCE(o.updated_at, o.created_at))) * 1440 > 30
                   ORDER BY o.updated_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("updated_at", d.get("created_at")))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "orders",
                    "escalation_type": "PAYMENT",
                    "escalation_source": "deposit_pending_verification",
                    "entity_type": "order",
                    "entity_id": d["id"],
                    "customer_id": d["customer_id"],
                    "title": f"定金待确认 — {d.get('customer_name', '')}",
                    "description": f"订单 {d.get('order_no','')} 已发送银行信息 {age}min，客户未确认付款",
                    "age_minutes": age,
                    "sla_deadline": "",
                    "context": {
                        "amount": d.get("deposit_amount", 0),
                        "order_no": d.get("order_no", ""),
                        "status": d.get("status", ""),
                        "deposit_status": d.get("deposit_status", ""),
                    },
                    "escalation_level": 0,
                })

            # 2. 未发银行信息 >2h（客户未回复 D）
            rows = conn.execute(
                """SELECT o.*, c.name as customer_name
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id=c.id
                   WHERE o.status='waiting_deposit'
                     AND (o.deposit_status IS NULL OR o.deposit_status='')
                     AND (julianday('now') - julianday(o.created_at)) * 1440 > 120
                   ORDER BY o.created_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("created_at"))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "orders",
                    "escalation_type": "PAYMENT",
                    "escalation_source": "deposit_not_sent",
                    "entity_type": "order",
                    "entity_id": d["id"],
                    "customer_id": d["customer_id"],
                    "title": f"定金未启动 — {d.get('customer_name', '')}",
                    "description": f"订单 {d.get('order_no','')} 创建 {age}min，客户未回复定金确认",
                    "age_minutes": age,
                    "sla_deadline": "",
                    "context": {
                        "amount": d.get("deposit_amount", 0),
                        "order_no": d.get("order_no", ""),
                    },
                    "escalation_level": 0,
                })

            conn.close()
        except Exception as e:
            logger.error(f"PAYMENT scan error: {e}")
        return events

    # ==================== EXECUTION Scanner ====================

    def _scan_execution(self):
        """扫描执行阻塞事件"""
        events = []
        try:
            from database import get_db
            conn = get_db()

            # 1. 生产未开始 >48h
            rows = conn.execute(
                """SELECT o.*, c.name as customer_name
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id=c.id
                   WHERE o.status='active'
                     AND (o.production_progress IS NULL OR o.production_progress=0)
                     AND (julianday('now') - julianday(
                         COALESCE(o.updated_at, o.created_at))) * 1440 > 2880
                   ORDER BY o.updated_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("updated_at", d.get("created_at")))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "orders",
                    "escalation_type": "EXECUTION",
                    "escalation_source": "production_not_started",
                    "entity_type": "order",
                    "entity_id": d["id"],
                    "customer_id": d["customer_id"],
                    "title": f"生产未开始 — {d.get('customer_name', '')}",
                    "description": f"订单 {d.get('order_no','')} 已确认 {age}min 但生产未启动",
                    "age_minutes": age,
                    "sla_deadline": "",
                    "context": {
                        "order_no": d.get("order_no", ""),
                        "production_progress": d.get("production_progress", 0),
                    },
                    "escalation_level": 0,
                })

            # 2. 生产中卡住（progress 未更新 >24h）
            rows = conn.execute(
                """SELECT o.*, c.name as customer_name
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id=c.id
                   WHERE o.status='in_production'
                     AND (julianday('now') - julianday(
                         COALESCE(o.updated_at, o.created_at))) * 1440 > 1440
                   ORDER BY o.updated_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("updated_at", d.get("created_at")))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "orders",
                    "escalation_type": "EXECUTION",
                    "escalation_source": "production_stuck",
                    "entity_type": "order",
                    "entity_id": d["id"],
                    "customer_id": d["customer_id"],
                    "title": f"生产停摆 — {d.get('customer_name', '')}",
                    "description": f"订单 {d.get('order_no','')} 生产中 {age}min 未更新进度",
                    "age_minutes": age,
                    "sla_deadline": d.get("production_end_date", ""),
                    "context": {
                        "order_no": d.get("order_no", ""),
                        "progress": d.get("production_progress", 0),
                        "end_date": d.get("production_end_date", ""),
                    },
                    "escalation_level": 0,
                })

            # 3. 发货延迟（已发货但 ETA 过了）
            rows = conn.execute(
                """SELECT o.*, c.name as customer_name
                   FROM orders o
                   LEFT JOIN customers c ON o.customer_id=c.id
                   WHERE o.status='shipped'
                     AND o.production_end_date != ''
                     AND o.production_end_date < datetime('now','localtime')
                   ORDER BY o.production_end_date ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("production_end_date"))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "orders",
                    "escalation_type": "EXECUTION",
                    "escalation_source": "shipping_delay",
                    "entity_type": "order",
                    "entity_id": d["id"],
                    "customer_id": d["customer_id"],
                    "title": f"发货延迟 — {d.get('customer_name', '')}",
                    "description": f"订单 {d.get('order_no','')} 预计 {d.get('production_end_date','')} 到货已过",
                    "age_minutes": age,
                    "sla_deadline": d.get("production_end_date", ""),
                    "context": {
                        "order_no": d.get("order_no", ""),
                        "shipping_info": d.get("shipping_info", ""),
                        "eta": d.get("production_end_date", ""),
                    },
                    "escalation_level": 0,
                })

            conn.close()
        except Exception as e:
            logger.error(f"EXECUTION scan error: {e}")
        return events

    # ==================== SLA Scanner ====================

    def _scan_sla(self):
        """扫描 SLA 时间风险事件"""
        events = []
        try:
            from database import get_db
            conn = get_db()

            # 从 escalation_events 表读取已超时或即将超时的 SLA
            rows = conn.execute(
                """SELECT e.*, c.name as customer_name, c.whatsapp
                   FROM escalation_events e
                   LEFT JOIN customers c ON e.customer_id=c.id
                   WHERE e.status IN ('open','assigned','in_progress')
                     AND e.sla_due_at != ''
                     AND e.sla_due_at <= datetime('now','localtime', '+1 hours')
                   ORDER BY e.sla_due_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                now = datetime.now()
                due = self._parse_ts(d.get("sla_due_at", ""))
                age = int((now - due).total_seconds() / 60) if due else 0
                is_overdue = age > 0
                events.append({
                    "source_id": d["id"],
                    "source_table": "escalation_events",
                    "escalation_type": "SLA",
                    "escalation_source": "sla_overdue" if is_overdue else "sla_at_risk",
                    "entity_type": "customer",
                    "entity_id": d["customer_id"] or 0,
                    "customer_id": d.get("customer_id"),
                    "title": f"{'⏰ SLA超时' if is_overdue else '⚠️ SLA即将超时'} — {d.get('customer_name','')}",
                    "description": f"[{d.get('category','GENERAL')}] {d.get('original_text','')[:80]}",
                    "age_minutes": age if is_overdue else 0,
                    "sla_deadline": d.get("sla_due_at", ""),
                    "escalation_level": d.get("escalation_level", 0),
                    "context": {
                        "category": d.get("category", ""),
                        "route_group": d.get("route_group", ""),
                        "event_id": d["id"],
                        "original_text": d.get("original_text", ""),
                        "is_overdue": is_overdue,
                    },
                })

            conn.close()
        except Exception as e:
            logger.error(f"SLA scan error: {e}")
        return events

    # ==================== SYSTEM Scanner ====================

    def _scan_system(self):
        """扫描系统异常事件"""
        events = []
        try:
            from database import get_db
            conn = get_db()

            # 1. 执行队列失败任务
            rows = conn.execute(
                """SELECT eq.*
                   FROM execution_queue eq
                   WHERE eq.status='failed'
                     AND eq.updated_at >= datetime('now','-7 days')
                   ORDER BY eq.updated_at DESC
                   LIMIT 20"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("created_at"))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "execution_queue",
                    "escalation_type": "SYSTEM",
                    "escalation_source": "execution_failed",
                    "entity_type": "task",
                    "entity_id": d["id"],
                    "customer_id": None,
                    "title": f"执行任务失败 — {d.get('task_type','')}",
                    "description": f"任务 {d.get('task_type','')} 重试 {d.get('retry_count',0)} 次后失败: {str(d.get('error',''))[:100]}",
                    "age_minutes": age,
                    "sla_deadline": "",
                    "escalation_level": 0,
                    "context": {
                        "task_type": d.get("task_type", ""),
                        "error": str(d.get("error", ""))[:200],
                        "retry_count": d.get("retry_count", 0),
                    },
                })

            # 2. 卡住的处理中任务（locked >30min）
            rows = conn.execute(
                """SELECT eq.*
                   FROM execution_queue eq
                   WHERE eq.status='processing'
                     AND eq.locked_at > 0
                     AND (julianday('now') - julianday(
                         datetime(eq.locked_at / 1000, 'unixepoch'))) * 1440 > 30
                   ORDER BY eq.locked_at ASC"""
            ).fetchall()
            for r in rows:
                d = dict(r)
                age = int((datetime.now() - self._parse_ts(d.get("created_at"))).total_seconds() / 60)
                events.append({
                    "source_id": d["id"],
                    "source_table": "execution_queue",
                    "escalation_type": "SYSTEM",
                    "escalation_source": "execution_stuck",
                    "entity_type": "task",
                    "entity_id": d["id"],
                    "customer_id": None,
                    "title": f"执行任务卡住 — {d.get('task_type','')}",
                    "description": f"任务 {d.get('task_type','')} 被 {d.get('locked_by','?')} 锁定超过 30min",
                    "age_minutes": age,
                    "sla_deadline": "",
                    "escalation_level": 0,
                    "context": {
                        "task_type": d.get("task_type", ""),
                        "locked_by": d.get("locked_by", ""),
                        "locked_at": d.get("locked_at", 0),
                    },
                })

            conn.close()
        except Exception as e:
            logger.error(f"SYSTEM scan error: {e}")
        return events

    # ==================== Helpers ====================

    @staticmethod
    def _parse_ts(ts_str):
        """安全解析时间字符串"""
        if not ts_str:
            return datetime.now()
        try:
            return datetime.strptime(str(ts_str)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                # 尝试 unix timestamp (毫秒)
                return datetime.fromtimestamp(float(ts_str) / 1000)
            except Exception:
                return datetime.now()


# ==================== Daemon Thread ====================

_UEE_DAEMON_RUNNING = False
_UEE_DAEMON_INTERVAL = 60  # seconds


def _uee_scanner_loop():
    """守护线程：每 60 秒扫描一次全量 escalation"""
    global _UEE_DAEMON_RUNNING
    _UEE_DAEMON_RUNNING = True
    logger.info("[UEE Scanner] Started (interval: %ds)", _UEE_DAEMON_INTERVAL)

    engine = UnifiedEscalationEngine()
    cycle_count = 0

    while _UEE_DAEMON_RUNNING:
        try:
            count = engine.scan_all()
            if count > 0:
                logger.info("[UEE Scanner] Found %d new escalations", count)
            cycle_count += 1
            if cycle_count % 30 == 0:  # 每 30min 打一次健康日志
                logger.info("[UEE Scanner] Alive — %d cycles completed", cycle_count)
        except Exception as e:
            logger.error("[UEE Scanner] Error: %s", e)

        time.sleep(_UEE_DAEMON_INTERVAL)

    logger.info("[UEE Scanner] Stopped")


def start_uee_scanner(interval=60):
    """启动 UEE 扫描守护线程"""
    global _UEE_DAEMON_INTERVAL, _UEE_DAEMON_RUNNING
    _UEE_DAEMON_INTERVAL = interval
    if _UEE_DAEMON_RUNNING:
        logger.warning("[UEE Scanner] Already running")
        return None
    t = threading.Thread(target=_uee_scanner_loop, daemon=True, name="UEEScanner")
    t.start()
    return t


def stop_uee_scanner():
    """停止 UEE 扫描"""
    global _UEE_DAEMON_RUNNING
    _UEE_DAEMON_RUNNING = False
    logger.info("[UEE Scanner] Stop signal sent")
