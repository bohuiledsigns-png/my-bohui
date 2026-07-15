"""WhatsApp 独立服务
长期运行，Chrome 永不重启，和 CRM 进程分离
启动后监听 127.0.0.1:15789，提供 HTTP API

使用方法:
  python whatsapp_server.py

或双击桌面快捷方式「启动WhatsApp服务」
"""
import sys
import os
import json
import threading
import time
import hmac
import hashlib
import urllib.request
import urllib.error

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ========= 从 .env 加载 Webhook Secret =========
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
_WEBHOOK_SECRET = os.environ.get("WHATSAPP_WEBHOOK_SECRET", "").encode("utf-8")
if not _WEBHOOK_SECRET:
    print("[WAServer][WARN] WHATSAPP_WEBHOOK_SECRET 未设置，webhook 请求将不含签名")

# ========= Flask 服务器 =========
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========= 导入 WhatsApp 引擎 =========
import whatsapp_engine as wa

_engine_started = False
_engine_lock = threading.Lock()
_CRM_URL = "http://127.0.0.1:5789"


def _on_message_from_whatsapp(chat_name, messages):
    """回调：监控发现新消息时，转发到 CRM 的接收接口（带 HMAC 签名）"""
    try:
        body = json.dumps({"chat_name": chat_name, "messages": messages}).encode("utf-8")
        # 计算 HMAC-SHA256 签名
        signature = hmac.new(_WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            f"{_CRM_URL}/api/whatsapp-incoming",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"[WAServer] 已转发消息 ({chat_name}) → CRM")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[WAServer] 转发消息到CRM ({e.code}): {body[:100]}")
    except Exception as e:
        print(f"[WAServer] 转发消息到CRM失败: {e}")


def _ensure_engine():
    """确保引擎已启动（线程安全）"""
    global _engine_started
    with _engine_lock:
        if not _engine_started:
            print("[WAServer] 启动 WhatsApp 引擎...")
            wa.start_monitor(_on_message_from_whatsapp)
            _engine_started = True
            print("[WAServer] 引擎启动完成")
            # 启动健康检查守护线程
            _start_health_check()


# ==================== v3 健康检查守护 ====================

_health_fail_count = 0

def _start_health_check():
    """启动后台健康检查线程（每 60 秒检查一次，异常时告警）"""
    def _health_loop():
        global _health_fail_count
        while _engine_started:
            time.sleep(60)
            try:
                h = wa.get_health()
                if h.get("warning_count", 0) > 0:
                    _health_fail_count += 1
                    warnings = ", ".join(h.get("warnings", []))
                    print(f"[WAHealth] ⚠️ 警告({_health_fail_count}): {warnings}")
                    if _health_fail_count >= 3:
                        print(f"[WAHealth] 🔴 持续异常({_health_fail_count}次)，建议检查 Chrome 状态")
                else:
                    if _health_fail_count > 0:
                        print(f"[WAHealth] ✅ 已恢复（之前 {_health_fail_count} 次警告）")
                    _health_fail_count = 0
            except Exception as e:
                print(f"[WAHealth] 健康检查异常: {e}")
    threading.Thread(target=_health_loop, daemon=True).start()


# ==================== API 路由 ====================

@app.route("/health")
def api_health():
    """健康检查（v3: 含详细状态）"""
    try:
        h = wa.get_health()
        return jsonify(h)
    except Exception:
        return jsonify({"ok": True, "healthy": True, "warnings": [], "warning_count": 0})


@app.route("/status")
def api_status():
    """引擎状态（v3: 含心跳/进程信息）"""
    if not _engine_started:
        return jsonify({"running": False, "logged_in": False, "started": False,
                        "alive": False, "heartbeat_ago_s": -1, "needs_reauth": False})
    try:
        s = wa.get_monitor_status()
        s["started"] = True
        return jsonify(s)
    except Exception as e:
        return jsonify({"running": False, "logged_in": False, "started": True,
                        "alive": False, "heartbeat_ago_s": -1, "needs_reauth": False,
                        "error": str(e)})


@app.route("/send", methods=["POST"])
def api_send():
    """发送文字消息"""
    _ensure_engine()
    data = request.json or {}
    text = data.get("text", "")
    contact = data.get("contact_name", "")
    if not text:
        return jsonify({"ok": False, "error": "text is required"}), 400
    try:
        wa.send_text(text, contact_name=contact)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/send-file", methods=["POST"])
def api_send_file():
    """发送文件/图片"""
    _ensure_engine()
    data = request.json or {}
    path = data.get("path", "")
    contact = data.get("contact_name", "")
    if not path:
        return jsonify({"ok": False, "error": "path is required"}), 400
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": f"文件不存在: {path}"}), 400
    try:
        wa.send_media_file(path, contact_name=contact)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/send-image", methods=["POST"])
def api_send_image():
    """发送图片（clipboard方式）"""
    _ensure_engine()
    data = request.json or {}
    path = data.get("path", "")
    contact = data.get("contact_name", "")
    if not path:
        return jsonify({"ok": False, "error": "path is required"}), 400
    try:
        wa.send_image_clipboard(path, contact_name=contact)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/read")
def api_read():
    """读取当前聊天消息"""
    _ensure_engine()
    try:
        result = wa.read_messages()
        return jsonify({"ok": True, "text": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/refresh", methods=["POST"])
def api_refresh():
    """刷新 WhatsApp 页面"""
    if _engine_started:
        try:
            ok = wa.refresh_whatsapp_page()
            return jsonify({"ok": ok})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "引擎未启动"})


@app.route("/logged-in")
def api_logged_in():
    """检查是否已登录"""
    if not _engine_started:
        return jsonify({"logged_in": False})
    try:
        return jsonify({"logged_in": wa.is_logged_in()})
    except:
        return jsonify({"logged_in": False})


@app.route("/qr")
def api_qr():
    """获取 WhatsApp 二维码（base64 PNG）+ 登录状态"""
    if not _engine_started:
        return jsonify({"qr": None, "logged_in": False})
    try:
        qr = wa.get_qr_base64()
        logged_in = wa.is_logged_in()
        return jsonify({"qr": qr, "logged_in": logged_in})
    except Exception as e:
        return jsonify({"qr": None, "logged_in": False, "error": str(e)})


@app.route("/unread")
def api_unread():
    """获取未读聊天列表"""
    _ensure_engine()
    try:
        unread = wa.get_unread_chats()
        return jsonify({"ok": True, "unread": unread})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ==================== 启动 ====================

if __name__ == "__main__":
    print("=" * 50)
    print("  GLOWFORGE WhatsApp 独立服务")
    print(f"  端口: 127.0.0.1:15789")
    print("  长期稳定运行，不受CRM重启影响")
    print("=" * 50)
    # 预启动引擎
    _ensure_engine()
    # 启动 Flask（非 debug 模式，避免重启）
    app.run(host="127.0.0.1", port=15789, debug=False)
