"""Commercial Reality Layer — API 路由

挂载于 /api/reality/ 下，提供履约追踪、资金生命周期、Stripe 付款的 REST 接口。
"""
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

from flask import jsonify, request

from . import reality_bp

logger = logging.getLogger("glowforge.commercial_reality.routes")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


def _get_tracker():
    """延迟获取 FulfillmentTracker 实例"""
    from .fulfillment import FulfillmentTracker
    return FulfillmentTracker(DB_PATH)


def _get_payment():
    """延迟获取 PaymentLifecycle 实例"""
    from .payment_lifecycle import PaymentLifecycle
    return PaymentLifecycle(DB_PATH)


# ═══════════════════════════════════════════
# 订单履约 API
# ═══════════════════════════════════════════

@reality_bp.route("/fulfillment/<int:order_id>", methods=["GET"])
def get_fulfillment(order_id):
    """获取订单履约详情"""
    tracker = _get_tracker()
    data = tracker.get_fulfillment(order_id)
    if data is None:
        return jsonify({"error": "未找到履约记录"}), 404
    return jsonify(data)


@reality_bp.route("/fulfillment", methods=["GET"])
def list_fulfillments():
    """获取所有履约列表，支持分页"""
    limit = request.args.get("limit", 50, type=int)
    tracker = _get_tracker()
    data = tracker.get_all_fulfillments(limit)
    return jsonify({"data": data, "total": len(data)})


@reality_bp.route("/fulfillment/tasks", methods=["GET"])
def list_active_tasks():
    """获取所有活跃任务（联合 orders + customers 表，按风险排序）"""
    tracker = _get_tracker()
    data = tracker.get_active_tasks()
    return jsonify({"data": data, "total": len(data)})


@reality_bp.route("/fulfillment/<int:order_id>", methods=["PUT"])
def update_fulfillment(order_id):
    """更新订单履约状态

    请求体：
    {
        "field": "production_status",    // production_status | qc_status | shipment_status | payment_status
        "value": "IN_PROGRESS",
        "note": "已安排车间生产"           // 可选：内部备注
    }
    """
    body = request.get_json(silent=True) or {}
    field = body.get("field", "")
    value = body.get("value", "")
    note = body.get("note", "")

    tracker = _get_tracker()
    field_map = {
        "production_status": tracker.update_production,
        "qc_status": tracker.update_qc,
        "shipment_status": tracker.update_shipment,
        "payment_status": tracker.update_payment,
    }

    updater = field_map.get(field)
    if not updater:
        return jsonify({"error": f"不支持的字段: {field}"}), 400

    # shipment 需要额外参数
    if field == "shipment_status":
        tracking_no = body.get("tracking_no", "")
        actual_date = body.get("actual_delivery_date", "")
        ok = tracker.update_shipment(order_id, value,
                                     tracking_no=tracking_no,
                                     actual_delivery_date=actual_date)
    else:
        ok = updater(order_id, value, note=note)

    if not ok:
        return jsonify({"error": "更新失败，请检查状态值是否合法"}), 400
    return jsonify({"ok": True})


@reality_bp.route("/fulfillment/<int:order_id>/risk", methods=["PUT"])
def set_fulfillment_risk(order_id):
    """设置风险等级

    请求体：
    {
        "level": "HIGH",        // LOW | MEDIUM | HIGH | CRITICAL
        "reason": "原材料延迟到货"
    }
    """
    body = request.get_json(silent=True) or {}
    level = body.get("level", "")
    reason = body.get("reason", "")

    tracker = _get_tracker()
    ok = tracker.set_risk(order_id, level, reason)
    if not ok:
        return jsonify({"error": "风险等级不合法"}), 400
    return jsonify({"ok": True})


@reality_bp.route("/fulfillment/<int:order_id>/unfulfillable", methods=["POST"])
def mark_unfulfillable(order_id):
    """标记订单为无法履约"""
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "")
    if not reason:
        return jsonify({"error": "必须提供原因"}), 400

    tracker = _get_tracker()
    ok = tracker.mark_unfulfillable(order_id, reason)
    if not ok:
        return jsonify({"error": "操作失败"}), 500
    return jsonify({"ok": True, "message": f"订单 {order_id} 已标记为无法履约"})


@reality_bp.route("/fulfillment/check-overdue", methods=["GET"])
def check_overdue():
    """检查并返回所有超期/即将超期订单"""
    tracker = _get_tracker()
    results = tracker.check_overdue()
    return jsonify({
        "data": results,
        "total": len(results),
        "at_risk_count": sum(1 for r in results if r["risk_level"] in ("HIGH", "CRITICAL")),
    })


@reality_bp.route("/fulfillment/dashboard", methods=["GET"])
def fulfillment_dashboard():
    """履约仪表盘聚合数据"""
    tracker = _get_tracker()
    data = tracker.get_dashboard()
    return jsonify(data)


# ═══════════════════════════════════════════
# 资金生命周期 API
# ═══════════════════════════════════════════

@reality_bp.route("/payment/<int:order_id>", methods=["GET"])
def get_payment(order_id):
    """获取订单资金生命周期"""
    pm = _get_payment()
    data = pm.get_payment(order_id)
    if data is None:
        return jsonify({"error": "未找到资金记录"}), 404
    return jsonify(data)


@reality_bp.route("/payment/<int:order_id>/stage", methods=["PUT"])
def update_payment_stage(order_id):
    """更新资金阶段"""
    body = request.get_json(silent=True) or {}
    stage = body.get("stage", "")
    detail = body.get("detail", {})
    pm = _get_payment()
    ok = pm.update_stage(order_id, stage, detail)
    if not ok:
        return jsonify({"error": "阶段不合法或更新失败"}), 400
    return jsonify({"ok": True})


@reality_bp.route("/payment/dashboard", methods=["GET"])
def payment_dashboard():
    """资金生命周期仪表盘"""
    pm = _get_payment()
    data = pm.get_dashboard()
    return jsonify(data)


# ═══════════════════════════════════════════
# Stripe 付款链接 API
# ═══════════════════════════════════════════

@reality_bp.route("/payment/<int:order_id>/generate-link", methods=["POST"])
def generate_payment_link(order_id):
    """生成 Stripe Checkout 付款链接

    请求体:
    {
        "type": "deposit"       // deposit | balance | full（默认 auto）
    }

    auto 逻辑：如果生命周期记录不存在或 stage=INTENT/COMMITMENT → deposit
              如果 stage=DEPOSIT_PAID → balance
              其他 → full
    """
    from .payment_gateway import StripePaymentGateway

    body = request.get_json(silent=True) or {}
    payment_type = body.get("type", "auto")

    # 获取订单信息
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            order = conn.execute(
                "SELECT id, order_no, total_amount, currency, customer_id FROM orders WHERE id=?",
                (order_id,),
            ).fetchone()
            if not order:
                return jsonify({"error": "订单不存在"}), 404
            order = dict(order)

            customer = conn.execute(
                "SELECT id, name, company, whatsapp FROM customers WHERE id=?",
                (order["customer_id"],),
            ).fetchone()
            customer = dict(customer) if customer else {}
        finally:
            conn.close()
    except Exception as e:
        logger.error("[Payment] get order %d failed: %s", order_id, e)
        return jsonify({"error": "获取订单信息失败"}), 500

    # 确定付款类型
    pm = _get_payment()
    lifecycle = pm.get_payment(order_id)
    currency = (order.get("currency") or "USD").lower()

    if payment_type == "auto":
        if not lifecycle or lifecycle.get("stage") in ("INTENT", "COMMITMENT"):
            payment_type = "deposit"
        elif lifecycle.get("stage") == "DEPOSIT_PAID":
            payment_type = "balance"
        else:
            payment_type = "full"

    # 计算金额
    total = order.get("total_amount") or 0
    if payment_type == "deposit":
        amount = total * 0.5
    elif payment_type == "balance":
        amount = total * 0.5
    else:
        amount = total

    # 确保有生命周期记录
    if not lifecycle:
        pm.create_payment(order_id, amount, currency, "COMMITMENT")

    # 生成 Stripe 链接
    gw = StripePaymentGateway()
    base_url = request.host_url.rstrip("/")

    if payment_type == "deposit":
        ok, result = gw.create_deposit_link(order_id, order.get("order_no", ""), total, currency, base_url)
    elif payment_type == "balance":
        ok, result = gw.create_balance_link(order_id, order.get("order_no", ""), amount, currency, base_url)
    else:
        ok, result = gw.create_full_link(order_id, order.get("order_no", ""), total, currency, base_url)

    if not ok:
        return jsonify({"error": result.get("error", "生成链接失败")}), 500

    # 将 payment_link 存入生命周期
    pm.update_stage(order_id, lifecycle["stage"] if lifecycle else "COMMITMENT", {
        "payment_link": result["url"],
    })

    return jsonify({
        "ok": True,
        "url": result["url"],
        "session_id": result["session_id"],
        "payment_type": payment_type,
        "amount": round(amount, 2),
    })


@reality_bp.route("/payment/<int:order_id>/send-link", methods=["POST"])
def send_payment_link(order_id):
    """通过 WhatsApp 发送已生成的付款链接给客户"""
    pm = _get_payment()
    lifecycle = pm.get_payment(order_id)
    if not lifecycle or not lifecycle.get("payment_link"):
        return jsonify({"error": "请先生成付款链接"}), 400

    # 获取客户信息
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            order = conn.execute(
                "SELECT o.order_no, o.total_amount, o.currency, c.name, c.whatsapp "
                "FROM orders o LEFT JOIN customers c ON o.customer_id = c.id "
                "WHERE o.id=?", (order_id,)
            ).fetchone()
            if not order:
                return jsonify({"error": "订单不存在"}), 404
            order = dict(order)
        finally:
            conn.close()
    except Exception as e:
        logger.error("[Payment] get customer for link send failed: %s", e)
        return jsonify({"error": "获取客户信息失败"}), 500

    customer_name = order.get("name") or "Customer"
    whatsapp = order.get("whatsapp") or ""
    if not whatsapp:
        return jsonify({"error": "客户无 WhatsApp 号码"}), 400

    # 确定付款类型（从当前阶段推断）
    stage = lifecycle.get("stage", "COMMITMENT")
    if stage in ("INTENT", "COMMITMENT"):
        payment_type = "deposit"
    elif stage == "DEPOSIT_PAID":
        payment_type = "balance"
    else:
        payment_type = "full"

    from .payment_gateway import StripePaymentGateway
    msg = StripePaymentGateway.format_payment_message(
        link_url=lifecycle["payment_link"],
        order_no=order.get("order_no") or f"#{order_id}",
        amount=lifecycle.get("amount", 0),
        currency=order.get("currency") or "USD",
        payment_type=payment_type,
        customer_name=customer_name,
        language="en",
    )

    # 后台发送（不阻塞 API）
    def _do_send():
        try:
            from whatsapp_engine import send_text
            send_text(msg, contact_name=customer_name)
            logger.info("[Payment] Link sent to %s for order %d", customer_name, order_id)
        except Exception as e:
            logger.error("[Payment] WhatsApp send failed for order %d: %s", order_id, e)

    threading.Thread(target=_do_send, daemon=True).start()

    return jsonify({"ok": True, "message": "付款链接已通过 WhatsApp 发送"})


@reality_bp.route("/payment/links", methods=["GET"])
def list_payment_links():
    """列出所有有付款链接的记录"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT pl.*, o.order_no, o.total_amount, o.currency,
                       c.name AS customer_name, c.whatsapp AS customer_whatsapp
                FROM payment_lifecycle pl
                LEFT JOIN orders o ON pl.order_id = o.id
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE pl.payment_link != ''
                ORDER BY pl.updated_at DESC
                LIMIT 100
            """).fetchall()
            return jsonify({"data": [dict(r) for r in rows], "total": len(rows)})
        finally:
            conn.close()
    except Exception as e:
        logger.error("[Payment] list links failed: %s", e)
        return jsonify({"data": [], "total": 0})


@reality_bp.route("/payment/pending-sends", methods=["GET"])
def pending_payment_sends():
    """获取待发送付款链接的订单列表

    AI 自动生成链接后，等待小王/老板手动发送。
    包含两批：
      - COMMITMENT/INTENT 阶段尚未生成链接的（自动触发生成）
      - 已生成链接但尚未发送的
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT pl.*, o.order_no, o.total_amount, o.currency,
                       c.name AS customer_name, c.whatsapp AS customer_whatsapp
                FROM payment_lifecycle pl
                LEFT JOIN orders o ON pl.order_id = o.id
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE pl.stage IN ('INTENT', 'COMMITMENT')
                  AND pl.amount > 0
                ORDER BY pl.updated_at ASC
                LIMIT 50
            """).fetchall()

            needs_gen = []
            pending_send = []

            for r in rows:
                d = dict(r)
                if d.get("payment_link"):
                    pending_send.append(d)
                else:
                    needs_gen.append(d)

            return jsonify({
                "needs_generation": needs_gen,
                "pending_send": pending_send,
                "total": len(rows),
            })
        finally:
            conn.close()
    except Exception as e:
        logger.error("[Payment] pending-sends failed: %s", e)
        return jsonify({"needs_generation": [], "pending_send": [], "total": 0})


@reality_bp.route("/payment/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Stripe Webhook 接收器（公开端点，无需登录）

    处理事件：
      - checkout.session.completed → 推进付款阶段
      - payment_intent.succeeded   → 兜底信号
    """
    from .payment_gateway import StripePaymentGateway

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    gw = StripePaymentGateway()
    ok, event_or_err = gw.verify_webhook_signature(payload, sig_header)
    if not ok:
        logger.warning("[StripeWebhook] Invalid signature: %s", event_or_err)
        return jsonify({"error": "Invalid signature"}), 400

    event = event_or_err
    event_type = event.get("type", "")
    event_id = event.get("id", "")
    logger.info("[StripeWebhook] Received %s (%s)", event_type, event_id)

    try:
        conn = sqlite3.connect(DB_PATH)

        # 幂等检查
        existing = conn.execute(
            "SELECT id FROM stripe_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if existing:
            conn.close()
            logger.info("[StripeWebhook] Already processed %s", event_id)
            return jsonify({"status": "already_processed"}), 200

        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            _handle_checkout_completed(conn, session, event_id)

        elif event_type == "payment_intent.succeeded":
            pi = event.get("data", {}).get("object", {})
            _handle_payment_intent_succeeded(conn, pi, event_id)

        else:
            # 记录但不处理其他事件
            conn.execute(
                "INSERT INTO stripe_events (event_id, type) VALUES (?, ?)",
                (event_id, event_type),
            )
            conn.commit()

        conn.close()
    except Exception as e:
        logger.error("[StripeWebhook] Processing failed: %s", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"received": True}), 200


def _handle_checkout_completed(conn, session, event_id):
    """处理 checkout.session.completed — 推进付款生命周期"""
    metadata = session.get("metadata", {})
    order_id_str = metadata.get("order_id", "0")
    payment_type = metadata.get("payment_type", "full")
    order_no = metadata.get("order_no", "")
    session_id = session.get("id", "")
    payment_intent = session.get("payment_intent", "")

    try:
        order_id = int(order_id_str)
    except (ValueError, TypeError):
        logger.error("[StripeWebhook] Invalid order_id in metadata: %s", order_id_str)
        return

    # 记录事件
    conn.execute(
        """INSERT INTO stripe_events (event_id, type, order_id, session_id, payment_intent_id)
           VALUES (?, ?, ?, ?, ?)""",
        (event_id, "checkout.session.completed", order_id, session_id, payment_intent),
    )
    conn.commit()

    # 推进付款阶段
    pm = _get_payment()
    lifecycle = pm.get_payment(order_id)
    if not lifecycle:
        logger.warning("[StripeWebhook] No lifecycle for order %d, creating", order_id)
        pm.create_payment(order_id, 0, "USD", "COMMITMENT")

    # 确定目标阶段
    current_stage = lifecycle["stage"] if lifecycle else "COMMITMENT"
    target_stage = "FULL_PAID" if payment_type in ("balance", "full") else "DEPOSIT_PAID"

    detail = {
        "paid_at": datetime.now().isoformat(),
        "transaction_ref": session_id,
        "payment_method": "Stripe",
        "payment_link": session.get("url", ""),
    }

    pm.update_stage(order_id, target_stage, detail)
    logger.info("[StripeWebhook] Order %d → %s (type=%s)", order_id, target_stage, payment_type)

    # 后台 WhatsApp 通知
    def _notify_paid():
        try:
            # 获取客户名
            c = conn.execute(
                "SELECT c.name FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE o.id=?",
                (order_id,),
            ).fetchone()
            name = c["name"] if c else "Customer"
            from whatsapp_engine import send_text
            from .payment_gateway import StripePaymentGateway

            msg = (
                f"✅ Payment Received! Order #{order_no}\n"
                f"Amount: ${lifecycle.get('amount', 0):,.2f}\n"
                f"Status: {target_stage}\n\n"
                f"Thank you! We'll start processing your order shortly.\n"
                f"GLOWFORGE Team"
            )
            send_text(msg, contact_name=name)
        except Exception as e:
            logger.error("[StripeWebhook] WhatsApp notify failed: %s", e)

    threading.Thread(target=_notify_paid, daemon=True).start()


def _handle_payment_intent_succeeded(conn, pi, event_id):
    """处理 payment_intent.succeeded — 作为兜底信号"""
    metadata = pi.get("metadata", {})
    order_id_str = metadata.get("order_id", "0")
    pi_id = pi.get("id", "")

    try:
        order_id = int(order_id_str)
    except (ValueError, TypeError):
        order_id = 0

    conn.execute(
        """INSERT INTO stripe_events (event_id, type, order_id, payment_intent_id)
           VALUES (?, ?, ?, ?)""",
        (event_id, "payment_intent.succeeded", order_id, pi_id),
    )
    conn.commit()

    if order_id:
        pm = _get_payment()
        lifecycle = pm.get_payment(order_id)
        if lifecycle and lifecycle.get("stage") in ("INTENT", "COMMITMENT", "DEPOSIT_PAID"):
            target = "DEPOSIT_PAID" if lifecycle["stage"] == "COMMITMENT" else "FULL_PAID"
            pm.update_stage(order_id, target, {
                "paid_at": datetime.now().isoformat(),
                "transaction_ref": pi_id,
                "payment_method": "Stripe",
            })
            logger.info("[StripeWebhook] PaymentIntent %s → order %d → %s", pi_id, order_id, target)


@reality_bp.route("/payment/links-admin")
def payment_links_admin_page():
    """付款链接管理页面"""
    from flask import render_template
    return render_template("admin_payment_links.html")


# ═══════════════════════════════════════════
# 监控页面
# ═══════════════════════════════════════════

@reality_bp.route("/monitor")
def monitor_page():
    """履约监控仪表盘页面"""
    from flask import render_template
    return render_template("reality_dashboard.html")


@reality_bp.route("/admin/approval")
def admin_approval_page():
    """小王/老板审批管理页面"""
    from flask import render_template
    return render_template("admin_approval.html")


# ═══════════════════════════════════════════
# 现实扰动事件处理
# ═══════════════════════════════════════════

@reality_bp.route("/event", methods=["POST"])
def handle_reality_event():
    """接收并处理现实扰动事件

    请求体:
    {
        "event_type": "CUSTOMER_DISPUTE",
        "context": {
            "order_id": 42,
            "reason": "货物损坏",
            "demand": "要求退款"
        }
    }

    支持的事件类型:
        WHATSAPP_BAN, WHATSAPP_OFFLINE,
        CUSTOMER_DISPUTE, COMPETITOR_PRICE,
        FACTORY_DELAY, ORDER_UNFULFILLABLE,
        PAYMENT_OVERDUE
    """
    body = request.get_json(silent=True) or {}
    event_type = body.get("event_type", "")
    context = body.get("context", {})

    if not event_type:
        return jsonify({"error": "缺少 event_type"}), 400

    from .reality_handler import RealityHandler
    handler = RealityHandler(DB_PATH)
    result = handler.handle_event(event_type, context)

    status = 200 if result.get("handled") else 202  # 202 = accepted but needs human
    return jsonify(result), status


# ═══════════════════════════════════════════
# 系统健康检查
# ═══════════════════════════════════════════

@reality_bp.route("/health", methods=["GET"])
def reality_health():
    """Commercial Reality 层自身健康状态"""
    from .reality_handler import RealityHandler
    handler = RealityHandler(DB_PATH)
    report = handler.run_health_check()
    return jsonify(report)


@reality_bp.route("/health/full", methods=["GET"])
def full_health_check():
    """全系统健康检查（与监控线程相同的检查逻辑）"""
    from .reality_handler import RealityHandler
    handler = RealityHandler(DB_PATH)
    report = handler.run_health_check()
    status_code = 200 if report["status"] == "ok" else 503
    return jsonify(report), status_code


# ═══════════════════════════════════════════
# WhatsApp 多号轮换管理 API
# ═══════════════════════════════════════════

@reality_bp.route("/wa/status", methods=["GET"])
def wa_rotation_status():
    """获取所有 WhatsApp 账号状态"""
    try:
        from .wa_rotation import manager as wa_manager
        status = wa_manager.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error("[WARotation] Status failed: %s", e)
        return jsonify({"error": str(e), "accounts": [], "active_id": 0}), 500


@reality_bp.route("/wa/failover", methods=["POST"])
def wa_manual_failover():
    """手动切换 WhatsApp 活跃账号"""
    try:
        from .wa_rotation import manager as wa_manager
        result = wa_manager.failover()
        return jsonify(result)
    except Exception as e:
        logger.error("[WARotation] Failover failed: %s", e)
        return jsonify({"error": str(e)}), 500


@reality_bp.route("/wa/account/<int:account_id>/toggle", methods=["POST"])
def wa_toggle_account(account_id):
    """启用/禁用某个 WhatsApp 账号"""
    try:
        from .wa_rotation import manager as wa_manager
        result = wa_manager.toggle_account(account_id)
        return jsonify(result)
    except Exception as e:
        logger.error("[WARotation] Toggle account failed: %s", e)
        return jsonify({"error": str(e)}), 500


@reality_bp.route("/wa/admin")
def wa_admin_page():
    """WhatsApp 多号轮换管理页面"""
    from flask import render_template
    return render_template("admin_wa_accounts.html")
