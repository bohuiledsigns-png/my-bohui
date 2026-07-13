"""Commercial Reality Layer — 商业履约安全层

不改动 V0-V9 任何核心代码，在现有系统上叠加一层 runtime wrapper，
专门处理"现实世界的不确定性"：

  1. FulfillmentTracker   — 订单履约追踪（生产/质检/发货/交期偏差）
  2. PaymentLifecycle     — 资金生命周期（意图→定金→尾款→退款/纠纷）
  3. RealityHandler       — 现实扰动处理（封号/比价/纠纷/延迟）+ 系统健康监控

使用方式（在 app.py 中）:
    from commercial_reality import init_commercial_reality
    init_commercial_reality(app, db_path)
"""
import logging
from flask import Blueprint

logger = logging.getLogger("glowforge.commercial_reality")

# API Blueprint — 统一挂载到 /api/reality/
reality_bp = Blueprint("commercial_reality", __name__)

from . import routes  # noqa: E402 — 注册路由


_INITIALIZED = False  # 防止重复初始化


def init_commercial_reality(app, db_path: str):
    """初始化商业履约安全层。

    1. 创建 DB 表（幂等）
    2. 注册 API Blueprint
    3. 启动后台监控任务（后续步骤添加）
    """
    global _INITIALIZED
    if _INITIALIZED:
        logger.info("[CommercialReality] Already initialized — skipping")
        return
    _INITIALIZED = True

    from .db import init_tables
    init_tables(db_path)

    app.register_blueprint(reality_bp, url_prefix="/api/reality")

    # 启动后台健康监控（默认 5 分钟轮询）
    try:
        from .reality_handler import start_health_monitor
        _health_thread = start_health_monitor(interval=300)
        logger.info("[CommercialReality] Health monitor started")
    except Exception as e:
        logger.warning("[CommercialReality] Health monitor start skipped: %s", e)

    logger.info("[CommercialReality] Layer initialized — tables + routes + health monitor ready")

    # 将 Stripe Webhook URL 注册为公开路径（无需登录）
    # 注意：不能 import app（会触发递归初始化），改用注入方式
    try:
        # 看看有没有 app 模块已经定义好 _PUBLIC_API_PATHS
        import sys
        if 'app' in sys.modules:
            _app_mod = sys.modules['app']
            if hasattr(_app_mod, '_PUBLIC_API_PATHS'):
                _app_mod._PUBLIC_API_PATHS.add("/api/reality/payment/webhook/stripe")
                logger.info("[Stripe] Webhook path registered as public")
            else:
                logger.warning("[Stripe] app module has no _PUBLIC_API_PATHS")
        else:
            logger.warning("[Stripe] app module not loaded yet — skip public path registration")
    except Exception as e:
        logger.warning("[Stripe] Could not register public path: %s", e)

    # 启动 WhatsApp 多号轮换
    try:
        from .wa_rotation import manager as wa_manager
        wa_manager.init_default_accounts(db_path)
        wa_manager.launch_all()
        wa_manager.start_health_monitor(interval=60)

        # Monkey-patch WhatsApp Engine → 全部路由到多号管理器，防止老引擎抢端口
        try:
            import whatsapp_engine
            we = whatsapp_engine

            we.send_text = wa_manager.send_text

            # 接管 is_logged_in — 查 WA rotation 的状态
            _orig_is_logged_in = we.is_logged_in
            def _wa_is_logged_in():
                try:
                    return wa_manager.all_healthy
                except Exception:
                    return _orig_is_logged_in()
            we.is_logged_in = _wa_is_logged_in

            # 接管 get_monitor_status — 返回多号版状态
            def _wa_monitor_status():
                try:
                    status = wa_manager.get_status()
                    online = sum(1 for a in status["accounts"] if a["logged_in"])
                    return {
                        "running": status["total"] > 0,
                        "logged_in": online > 0,
                        "alive": online > 0,
                        "online_accounts": online,
                        "total_accounts": status["total"],
                        "active_id": status["active_id"],
                        "subprocess_alive": True,
                    }
                except Exception:
                    return {"running": False, "logged_in": False, "alive": False}
            we.get_monitor_status = _wa_monitor_status

            # 接管 start_monitor — 直接 no-op（WA rotation 自己管）
            def _wa_start_monitor(callback=None):
                logger.info("[WARotation] start_monitor called — ignored (WA rotation manages health)")
            we.start_monitor = _wa_start_monitor

            # 重要：app.py 已经 from whatsapp_engine import start_monitor（本地引用），
            # 必须同时注入到 app 模块的命名空间
            try:
                import sys
                if 'app' in sys.modules:
                    sys.modules['app'].start_monitor = _wa_start_monitor
                    # 同样修复 is_logged_in
                    sys.modules['app'].is_logged_in = _wa_is_logged_in
                    sys.modules['app'].get_monitor_status = _wa_monitor_status
                    logger.info("[WARotation] app.py namespace also patched")
            except Exception:
                pass

            logger.info("[WARotation] send_text + is_logged_in + get_monitor_status + start_monitor monkey-patched")
        except Exception as e:
            logger.warning("[WARotation] Monkey-patch skipped: %s", e)

        logger.info("[WARotation] Manager initialized")
    except Exception as e:
        logger.warning("[WARotation] Init skipped: %s", e)
