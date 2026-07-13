"""StripePaymentGateway — Stripe Checkout 付款链接生成器

与 payment_lifecycle 状态机配合使用：
  create_deposit_link  → 生成 50% 定金链接
  create_balance_link  → 生成 50% 尾款链接
  create_full_link     → 生成 100% 全额链接

密钥加载策略（同 app.py 的 FLASK_SECRET_KEY 模式）:
  1. 环境变量 STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET
  2. 回退到项目根目录的 .stripe_key / .stripe_webhook_secret 文件
  3. 都不存在则标记为未配置（不崩溃）
"""
import json
import logging
import os

logger = logging.getLogger("glowforge.commercial_reality.payment_gateway")

# ── WhatsApp 消息模板 ──
_PAYMENT_LINK_TEMPLATES = {
    "en": (
        "Dear {name},\n\n"
        "Your payment link for order {order_no} is ready:\n"
        "{link}\n\n"
        "Amount: {currency}{amount:,.2f}\n"
        "({payment_type})\n\n"
        "Please complete the payment at your earliest convenience.\n"
        "The link will expire in 24 hours.\n\n"
        "Thank you for your business!\n"
        "GLOWFORGE Team"
    ),
    "zh": (
        "尊敬的{name}，\n\n"
        "您订单 {order_no} 的付款链接已生成：\n"
        "{link}\n\n"
        "金额：{currency}{amount:,.2f}\n"
        "（{payment_type}）\n\n"
        "请尽快完成付款，链接24小时内有效。\n\n"
        "感谢您的支持！\n"
        "GLOWFORGE 团队"
    ),
}

_PAYMENT_TYPE_LABELS = {
    "deposit": {"en": "50% Deposit", "zh": "50% 定金"},
    "balance": {"en": "50% Balance", "zh": "50% 尾款"},
    "full": {"en": "Full Payment", "zh": "全额付款"},
}


class StripePaymentGateway:
    """Stripe 付款链接网关

    用法:
        gw = StripePaymentGateway()
        ok, result = gw.create_deposit_link(
            order_id=42, order_no="ORD-001",
            total_amount=1500.00, currency="usd",
            base_url="http://localhost:5000"
        )
        if ok:
            print(result["url"])  # Stripe Checkout URL
    """

    def __init__(self):
        self._ready = False
        self._secret_key = ""
        self._webhook_secret = ""
        self._pending = True  # 首次调用时加载

    def _ensure_initialized(self):
        """延迟加载密钥（首次调用时执行）"""
        if not self._pending:
            return
        self._pending = False

        # 1. 环境变量
        self._secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self._webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

        # 2. 文件回退（同 FLASK_SECRET_KEY 模式）
        if not self._secret_key:
            try:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                key_file = os.path.join(base, ".stripe_key")
                if os.path.isfile(key_file):
                    with open(key_file, "r") as f:
                        self._secret_key = f.read().strip()
            except Exception:
                pass

        if not self._webhook_secret:
            try:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                wh_file = os.path.join(base, ".stripe_webhook_secret")
                if os.path.isfile(wh_file):
                    with open(wh_file, "r") as f:
                        self._webhook_secret = f.read().strip()
            except Exception:
                pass

        if not self._secret_key:
            logger.warning("[StripeGateway] STRIPE_SECRET_KEY not configured")
            return

        self._ready = True
        logger.info("[StripeGateway] Initialized (key: %s...)",
                    self._secret_key[:8] if len(self._secret_key) > 8 else "present")

    # ── 通用 Checkout Session ──

    def create_checkout_session(
        self, amount_cents: int, currency: str,
        metadata: dict,
        success_url: str = "",
        cancel_url: str = "",
    ) -> tuple:
        """创建 Stripe Checkout Session

        Args:
            amount_cents: 金额（美分）
            currency: 货币代码（小写，如 "usd"）
            metadata: 附加到 session 的元数据
            success_url: 支付成功跳转 URL
            cancel_url: 取消支付跳转 URL

        Returns:
            (True, {"url": str, "session_id": str})
            (False, {"error": str})
        """
        self._ensure_initialized()
        if not self._ready:
            return False, {"error": "Stripe 未配置，请设置 STRIPE_SECRET_KEY"}

        try:
            import stripe
            stripe.api_key = self._secret_key

            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": f"GLOWFORGE Order #{metadata.get('order_no', '')}",
                            "description": f"Payment for order {metadata.get('order_no', '')} — {metadata.get('payment_type', 'order')}",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                metadata=metadata,
                success_url=success_url or "https://wa.bohui-sign.com/payment/success",
                cancel_url=cancel_url or "https://wa.bohui-sign.com/payment/cancelled",
            )

            logger.info("[StripeGateway] Created session %s for order %s (amount=%d %s)",
                        session.id, metadata.get("order_no", "?"), amount_cents, currency)
            return True, {"url": session.url, "session_id": session.id}

        except Exception as e:
            logger.error("[StripeGateway] create_checkout_session failed: %s", e)
            return False, {"error": str(e)}

    # ── 专用链接生成 ──

    def create_deposit_link(
        self, order_id: int, order_no: str,
        total_amount: float, currency: str = "usd",
        base_url: str = "",
    ) -> tuple:
        """生成 50% 定金付款链接"""
        deposit_cents = self._cents(total_amount * 0.5)
        return self.create_checkout_session(
            amount_cents=deposit_cents,
            currency=currency,
            metadata={
                "order_id": str(order_id),
                "order_no": order_no,
                "payment_type": "deposit",
            },
            success_url=f"{base_url}/api/reality/payment/links-admin?paid=1",
            cancel_url=f"{base_url}/api/reality/payment/links-admin?cancelled=1",
        )

    def create_balance_link(
        self, order_id: int, order_no: str,
        balance_amount: float, currency: str = "usd",
        base_url: str = "",
    ) -> tuple:
        """生成 50% 尾款付款链接"""
        balance_cents = self._cents(balance_amount)
        return self.create_checkout_session(
            amount_cents=balance_cents,
            currency=currency,
            metadata={
                "order_id": str(order_id),
                "order_no": order_no,
                "payment_type": "balance",
            },
            success_url=f"{base_url}/api/reality/payment/links-admin?paid=1",
            cancel_url=f"{base_url}/api/reality/payment/links-admin?cancelled=1",
        )

    def create_full_link(
        self, order_id: int, order_no: str,
        total_amount: float, currency: str = "usd",
        base_url: str = "",
    ) -> tuple:
        """生成全额付款链接"""
        total_cents = self._cents(total_amount)
        return self.create_checkout_session(
            amount_cents=total_cents,
            currency=currency,
            metadata={
                "order_id": str(order_id),
                "order_no": order_no,
                "payment_type": "full",
            },
            success_url=f"{base_url}/api/reality/payment/links-admin?paid=1",
            cancel_url=f"{base_url}/api/reality/payment/links-admin?cancelled=1",
        )

    # ── Webhook 验证 ──

    def verify_webhook_signature(self, payload: str, sig_header: str) -> tuple:
        """验证 Stripe Webhook 签名

        Returns:
            (True, event_dict)
            (False, error_message)
        """
        self._ensure_initialized()
        if not self._ready or not self._webhook_secret:
            return False, "Webhook secret not configured"

        try:
            import stripe
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret
            )
            return True, json.loads(str(event))

        except Exception as e:
            logger.error("[StripeGateway] Webhook signature verification failed: %s", e)
            return False, f"Signature verification failed: {e}"

    # ── 消息格式化 ──

    @staticmethod
    def format_payment_message(
        link_url: str, order_no: str,
        amount: float, currency: str = "USD",
        payment_type: str = "deposit",
        customer_name: str = "",
        language: str = "en",
    ) -> str:
        """生成发送给客户的付款链接 WhatsApp 消息

        Args:
            payment_type: "deposit" / "balance" / "full"
            language: "en" / "zh"
        """
        templates = _PAYMENT_LINK_TEMPLATES.get(language, _PAYMENT_LINK_TEMPLATES["en"])
        type_label = _PAYMENT_TYPE_LABELS.get(payment_type, {}).get(language, payment_type)
        return templates.format(
            name=customer_name or "Customer",
            order_no=order_no,
            link=link_url,
            currency=currency,
            amount=amount,
            payment_type=type_label,
        )

    # ── 辅助 ──

    @staticmethod
    def _cents(amount: float) -> int:
        return max(50, int(round(amount * 100)))  # 最低 50 美分（Stripe 下限）
