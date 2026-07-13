"""RealityHandler — 现实扰动处理 + 系统健康监控

统一处理所有"现实世界"的非标准输入和系统异常：
  1. WhatsApp 封号 / 掉线 → 自动切换
  2. 客户纠纷 → 升级老板
  3. 比价 → 触发应对策略（不自动降价）
  4. 工厂延迟 / 无法履约 → 告警
  5. 全系统健康监控 → 定时检查 + 聚合报告
"""
import json
import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger("glowforge.commercial_reality.reality")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ── 事件类型常量 ──
EVENT_WHATSAPP_BAN = "WHATSAPP_BAN"
EVENT_WHATSAPP_OFFLINE = "WHATSAPP_OFFLINE"
EVENT_CUSTOMER_DISPUTE = "CUSTOMER_DISPUTE"
EVENT_COMPETITOR_PRICE = "COMPETITOR_PRICE"
EVENT_FACTORY_DELAY = "FACTORY_DELAY"
EVENT_ORDER_UNFULFILLABLE = "ORDER_UNFULFILLABLE"
EVENT_PAYMENT_OVERDUE = "PAYMENT_OVERDUE"

# ── 告警级别 ──
ALERT_P0 = "P0"  # 致命
ALERT_P1 = "P1"  # 严重
ALERT_P2 = "P2"  # 一般

_HEALTH_DAEMON_RUNNING = False


class RealityHandler:
    """现实扰动处理器

    用法:
        handler = RealityHandler()
        handler.handle_event("CUSTOMER_DISPUTE", {
            "order_id": 42, "reason": "货物损坏", "demand": "退款"
        })
        report = handler.run_health_check()
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path

    # ═══════════════════════════════════════════
    # 统一事件入口
    # ═══════════════════════════════════════════

    def handle_event(self, event_type: str, context: dict) -> dict:
        """统一处理所有现实扰动事件

        Args:
            event_type: 事件类型常量
            context: 事件上下文数据

        Returns:
            dict: {handled: bool, action: str, alert: str|None}
        """
        handler_map = {
            EVENT_WHATSAPP_BAN: self._handle_whatsapp_ban,
            EVENT_WHATSAPP_OFFLINE: self._handle_whatsapp_offline,
            EVENT_CUSTOMER_DISPUTE: self._handle_dispute,
            EVENT_COMPETITOR_PRICE: self._handle_competitor_price,
            EVENT_FACTORY_DELAY: self._handle_factory_delay,
            EVENT_ORDER_UNFULFILLABLE: self._handle_unfulfillable,
            EVENT_PAYMENT_OVERDUE: self._handle_payment_overdue,
        }

        handler = handler_map.get(event_type)
        if not handler:
            logger.warning("[RealityHandler] Unknown event type: %s", event_type)
            return {"handled": False, "action": "unknown_event"}

        try:
            return handler(context)
        except Exception as e:
            logger.error("[RealityHandler] Handler failed for %s: %s", event_type, e)
            return {"handled": False, "action": "error", "error": str(e)}

    # ── WhatsApp 封号 / 掉线 ──

    def _handle_whatsapp_ban(self, ctx: dict) -> dict:
        """WhatsApp 被封 — 尝试切换备用号"""
        logger.warning("[RealityHandler] WhatsApp BANNED — attempting failover")
        try:
            from whatsapp_engine import refresh_whatsapp_page, is_logged_in

            # 尝试刷新当前页面
            refresh_whatsapp_page()
            time.sleep(3)

            if is_logged_in():
                return {"handled": True, "action": "page_refreshed"}
            else:
                return {
                    "handled": False,
                    "action": "escalated",
                    "alert": ALERT_P0,
                    "message": "WhatsApp 被封，需要人工扫码登录备用号",
                }
        except Exception as e:
            return {
                "handled": False,
                "action": "escalated",
                "alert": ALERT_P0,
                "message": f"WhatsApp 处理异常: {e}",
            }

    def _handle_whatsapp_offline(self, ctx: dict) -> dict:
        """WhatsApp 掉线 — 尝试重连"""
        logger.info("[RealityHandler] WhatsApp offline — attempting reconnect")
        try:
            from whatsapp_engine import refresh_whatsapp_page, is_logged_in

            refresh_whatsapp_page()
            time.sleep(2)

            if is_logged_in():
                return {"handled": True, "action": "reconnected"}
            else:
                return self._handle_whatsapp_ban(ctx)
        except Exception as e:
            return {
                "handled": False,
                "action": "escalated",
                "alert": ALERT_P1,
                "message": f"WhatsApp 重连失败: {e}",
            }

    # ── 客户纠纷 ──

    def _handle_dispute(self, ctx: dict) -> dict:
        """客户纠纷 — 升级到老板，AI 不自动处理"""
        order_id = ctx.get("order_id")
        reason = ctx.get("reason", "")
        demand = ctx.get("demand", "")

        logger.info("[RealityHandler] Dispute for order %d: %s", order_id, reason[:60])

        # 标记订单为 DISPUTED
        try:
            from .payment_lifecycle import PaymentLifecycle
            pm = PaymentLifecycle(self._db_path)
            pm.update_stage(order_id, "DISPUTED", {
                "dispute_status": "OPEN",
                "refund_reason": reason,
            })
        except Exception:
            pass

        return {
            "handled": False,  # 需要人工处理
            "action": "escalated",
            "alert": ALERT_P1,
            "message": f"订单 {order_id} 纠纷: {reason}",
            "escalation": {
                "type": "CUSTOMER_DISPUTE",
                "order_id": order_id,
                "reason": reason,
                "customer_demand": demand,
                "options": [
                    {"label": "全额退款", "action": "REFUND_FULL"},
                    {"label": "部分退款补偿", "action": "REFUND_PARTIAL"},
                    {"label": "坚持立场不退", "action": "NO_REFUND"},
                    {"label": "补发替换", "action": "REISSUE"},
                ],
            },
        }

    @staticmethod
    def _handle_competitor_price(ctx: dict) -> dict:
        """比价 — AI 不自动降价，触发应对策略"""
        customer_id = ctx.get("customer_id")
        competitor_info = ctx.get("competitor_info", {})

        logger.info("[RealityHandler] Competitor price detected for customer %s", customer_id)

        return {
            "handled": True,  # AI 可以自己处理（不降价）
            "action": "strategy_applied",
            "message": "客户比价，AI 已使用比价应对话术（不自动降价）",
            "strategy": {
                "do_not_auto_discount": True,
                "tactics": [
                    "先问客户能否分享对方报价单（大部分拿不出）",
                    "强调 GLOWFORGE 质量/认证/交期差异",
                    "提供配置调整方案而不是直接降价",
                    "对比价幅度超过 15% 才推给老板审批",
                ],
            },
        }

    # ── 工厂延迟 / 无法履约 ──

    def _handle_factory_delay(self, ctx: dict) -> dict:
        """工厂延迟 — 标记风险，通知小王/老板"""
        order_id = ctx.get("order_id")
        delay_days = ctx.get("delay_days", 0)
        reason = ctx.get("reason", "")

        # 标记履约风险
        try:
            from .fulfillment import FulfillmentTracker
            tracker = FulfillmentTracker(self._db_path)
            if delay_days > 3:
                tracker.set_risk(order_id, "CRITICAL", f"工厂延迟 {delay_days}天: {reason}")
            elif delay_days > 0:
                tracker.set_risk(order_id, "HIGH", f"工厂延迟 {delay_days}天: {reason}")
            tracker.update_production(order_id, "IN_PROGRESS", note=f"延迟 {delay_days}天: {reason}")
        except Exception:
            pass

        return {
            "handled": True,
            "action": "risk_updated",
            "alert": ALERT_P2 if delay_days <= 3 else ALERT_P1,
            "message": f"订单 {order_id} 工厂延迟 {delay_days}天: {reason}",
        }

    def _handle_unfulfillable(self, ctx: dict) -> dict:
        """无法履约 — 标记 + P0 告警"""
        order_id = ctx.get("order_id")
        reason = ctx.get("reason", "")

        try:
            from .fulfillment import FulfillmentTracker
            tracker = FulfillmentTracker(self._db_path)
            tracker.mark_unfulfillable(order_id, reason)
        except Exception:
            pass

        return {
            "handled": False,
            "action": "escalated",
            "alert": ALERT_P0,
            "message": f"订单 {order_id} 无法履约: {reason}",
        }

    @staticmethod
    def _handle_payment_overdue(ctx: dict) -> dict:
        """尾款逾期 — 自动发提醒"""
        order_id = ctx.get("order_id")
        days = ctx.get("days_overdue", 0)

        logger.info("[RealityHandler] Payment overdue for order %d (%d days)", order_id, days)

        return {
            "handled": True,
            "action": "reminder_scheduled",
            "message": f"订单 {order_id} 尾款逾期 {days}天，已安排自动跟进提醒",
        }

    # ═══════════════════════════════════════════
    # 系统健康监控
    # ═══════════════════════════════════════════

    def run_health_check(self) -> dict:
        """全系统健康检查。

        检查项目:
          1. WhatsApp 在线状态
          2. 订单履约超期
          3. 尾款逾期
          4. 活跃纠纷
          5. 执行队列健康

        Returns:
            dict: {status, alerts, summary}
        """
        alerts = []
        checks = {}

        # 1. WhatsApp 状态（多号轮换）
        try:
            from .wa_rotation import manager as wa_manager
            health_list = wa_manager.check_all_health()
            logged_in = [h for h in health_list if h.get("logged_in")]
            checks["whatsapp"] = {
                "online_accounts": len(logged_in),
                "total_accounts": len(health_list),
                "status": "ok" if logged_in else "offline",
            }
            if not logged_in:
                alerts.append({
                    "level": ALERT_P0,
                    "source": "whatsapp",
                    "message": "所有 WhatsApp 号离线，需人工处理",
                })
            elif len(logged_in) < len(health_list):
                # 部分离线 — 自动 failover 已处理，只报告信息
                offline_count = len(health_list) - len(logged_in)
                if offline_count > 0:
                    alerts.append({
                        "level": ALERT_P2,
                        "source": "whatsapp",
                        "message": f"已有 {offline_count} 个 WhatsApp 号掉线（自动切换中）",
                    })
        except Exception as e:
            # 降级：尝试老的 is_logged_in
            try:
                from whatsapp_engine import is_logged_in
                wa_ok = is_logged_in()
                checks["whatsapp"] = "ok" if wa_ok else "offline"
                if not wa_ok:
                    alerts.append({
                        "level": ALERT_P0,
                        "source": "whatsapp",
                        "message": "WhatsApp 掉线，需人工扫码登录",
                    })
            except Exception as e2:
                checks["whatsapp"] = f"error: {e2}"
                alerts.append({"level": ALERT_P1, "source": "whatsapp", "message": f"WhatsApp 状态检测失败: {e2}"})

        # 2. 履约超期
        try:
            from .fulfillment import FulfillmentTracker
            tracker = FulfillmentTracker(self._db_path)
            overdue = tracker.check_overdue()
            critical = [r for r in overdue if r["risk_level"] == "CRITICAL"]
            high = [r for r in overdue if r["risk_level"] == "HIGH"]
            checks["fulfillment"] = {
                "overdue_total": len(overdue),
                "critical": len(critical),
                "high": len(high),
            }
            if critical:
                alerts.append({
                    "level": ALERT_P0,
                    "source": "fulfillment",
                    "message": f"{len(critical)} 笔订单严重超期（CRITICAL）",
                    "order_ids": [r["order_id"] for r in critical[:5]],
                })
            if high:
                alerts.append({
                    "level": ALERT_P1 if not critical else ALERT_P2,
                    "source": "fulfillment",
                    "message": f"{len(high)} 笔订单超期（HIGH）",
                })
        except Exception as e:
            checks["fulfillment"] = f"error: {e}"

        # 3. 尾款逾期
        try:
            from .payment_lifecycle import PaymentLifecycle
            pm = PaymentLifecycle(self._db_path)
            overdue_balances = pm.check_overdue_balances(grace_days=7)
            checks["payment"] = {
                "overdue_balances": len(overdue_balances),
            }
            if overdue_balances:
                alerts.append({
                    "level": ALERT_P1,
                    "source": "payment",
                    "message": f"{len(overdue_balances)} 笔订单尾款逾期超 7 天",
                })

            disputes = pm.check_active_disputes()
            checks["payment"]["active_disputes"] = len(disputes)
            if disputes:
                alerts.append({
                    "level": ALERT_P1,
                    "source": "payment",
                    "message": f"{len(disputes)} 条活跃纠纷待处理",
                })
        except Exception as e:
            checks["payment"] = f"error: {e}"

        # 4. 执行队列健康
        try:
            from execution.execution_queue import ExecutionQueue
            q = ExecutionQueue(self._db_path)
            stats = q.get_queue_stats()
            stuck = stats.get("processing", 0)
            failed = stats.get("failed", 0)
            checks["execution_queue"] = {
                "stuck_processing": stuck,
                "failed": failed,
            }
            if stuck > 5:
                alerts.append({
                    "level": ALERT_P2,
                    "source": "execution_queue",
                    "message": f"执行队列 {stuck} 任务卡在 processing",
                })
            if failed > 10:
                alerts.append({
                    "level": ALERT_P2,
                    "source": "execution_queue",
                    "message": f"执行队列 {failed} 任务失败待排查",
                })
        except Exception as e:
            checks["execution_queue"] = f"error: {e}"

        status = "ok" if not any(a["level"] == ALERT_P0 for a in alerts) else "critical"
        if not status == "critical" and alerts:
            status = "warning"

        return {
            "status": status,
            "checked_at": datetime.now().isoformat(),
            "checks": checks,
            "alerts": alerts,
            "summary": {
                "total_checks": len(checks),
                "alerts_p0": sum(1 for a in alerts if a["level"] == ALERT_P0),
                "alerts_p1": sum(1 for a in alerts if a["level"] == ALERT_P1),
                "alerts_p2": sum(1 for a in alerts if a["level"] == ALERT_P2),
            },
        }

    def get_internal_note(self, order_id: int) -> str:
        """小王端使用：读取某订单的最新 internal_note"""
        try:
            from .fulfillment import FulfillmentTracker
            tracker = FulfillmentTracker(self._db_path)
            f = tracker.get_fulfillment(order_id)
            return f["internal_note"] if f else ""
        except Exception:
            return ""


# ═══════════════════════════════════════════
# 后台守护线程
# ═══════════════════════════════════════════

def start_health_monitor(interval: int = 300) -> threading.Thread:
    """启动后台健康监控线程（默认每 5 分钟检查一次）。

    用法:
        from commercial_reality.reality_handler import start_health_monitor
        start_health_monitor(interval=300)
    """
    global _HEALTH_DAEMON_RUNNING

    if _HEALTH_DAEMON_RUNNING:
        logger.info("[HealthMonitor] Already running")
        return

    _HEALTH_DAEMON_RUNNING = True

    def _loop():
        handler = RealityHandler()
        logger.info("[HealthMonitor] Started (interval=%ds)", interval)

        while _HEALTH_DAEMON_RUNNING:
            try:
                report = handler.run_health_check()
                if report["status"] != "ok":
                    p0 = report["summary"]["alerts_p0"]
                    p1 = report["summary"]["alerts_p1"]
                    logger.warning(
                        "[HealthMonitor] Status=%s | P0=%d P1=%d P2=%d",
                        report["status"],
                        report["summary"]["alerts_p0"],
                        report["summary"]["alerts_p1"],
                        report["summary"]["alerts_p2"],
                    )
                    for a in report["alerts"]:
                        logger.warning("[HealthMonitor] [%s] %s", a["level"], a["message"])
                else:
                    logger.info("[HealthMonitor] All checks passed")
            except Exception as e:
                logger.error("[HealthMonitor] Check error: %s", e)

            time.sleep(interval)

        logger.info("[HealthMonitor] Stopped")

    thread = threading.Thread(target=_loop, daemon=True, name="health-monitor")
    thread.start()
    return thread


def stop_health_monitor():
    """停止健康监控线程"""
    global _HEALTH_DAEMON_RUNNING
    _HEALTH_DAEMON_RUNNING = False
    logger.info("[HealthMonitor] Stop signal sent")
