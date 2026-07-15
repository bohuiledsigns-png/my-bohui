"""Alert Channel — 多渠道告警分发

支持后端: Telegram / PushPlus / 文件降级
无配置时静默，永不因告警而崩溃。

用法:
    from safety.alert_channel import send_alert
    send_alert("CRM App is down!", severity="critical")
"""
import logging
import os
import threading
import time
import json
from datetime import datetime

logger = logging.getLogger("glowforge.alert")

# ── 限速 ──
_last_sent = {}  # channel -> timestamp
_RATE_LIMIT = 60  # 每条通道最小间隔（秒）


def _rate_limited(channel):
    """检查指定通道是否在限速中"""
    now = time.time()
    last = _last_sent.get(channel, 0)
    if now - last < _RATE_LIMIT:
        return True
    _last_sent[channel] = now
    return False


def _send_telegram(message, severity):
    """通过 Telegram Bot 发送告警"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    if _rate_limited("telegram"):
        return False

    try:
        import urllib.request
        payload = json.dumps({
            "chat_id": chat_id,
            "text": f"[{severity.upper()}] {message}",
            "parse_mode": "HTML",
        }).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        logger.warning("Telegram alert failed: %s", e)
        return False


def _send_pushplus(message, severity):
    """通过 PushPlus 发送告警"""
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        return False

    if _rate_limited("pushplus"):
        return False

    try:
        import urllib.request
        payload = json.dumps({
            "token": token,
            "title": f"[{severity.upper()}] GLOWFORGE Alert",
            "content": message,
        }).encode()
        req = urllib.request.Request(
            "https://www.pushplus.plus/send",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        logger.warning("PushPlus alert failed: %s", e)
        return False


def _write_file(message, severity):
    """文件降级 — 写入 logs/alert.log"""
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "alert.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} [{severity}] {message}\n")
        return True
    except OSError:
        return False


def send_alert(message, severity="info"):
    """分发告警到所有已配置的通道

    参数:
        message:  告警内容
        severity: info | warning | critical

    返回:
        dict: {telegram: bool, pushplus: bool, file: bool}
    """
    result = {}

    # 异步发送（不阻塞调用方）
    def _do_send():
        result["telegram"] = _send_telegram(message, severity)
        result["pushplus"] = _send_pushplus(message, severity)
        result["file"] = _write_file(message, severity)
        logger.info(
            "Alert sent: %s",
            severity,
            extra={"extra_fields": {"severity": severity, "result": result}},
        )

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()
    return result
