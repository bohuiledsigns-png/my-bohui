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

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ========= Flask 服务器 =========
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========= 导入 WhatsApp 引擎 =========
import whatsapp_engine as wa

_engine_started = False
_engine_lock = threading.Lock()


def _ensure_engine():
    """确保引擎已启动（线程安全）"""
    global _engine_started
    with _engine_lock:
        if not _engine_started:
            print("[WAServer] 启动 WhatsApp 引擎...")
            wa.start_monitor()
            _engine_started = True
            print("[WAServer] 引擎启动完成")


# ==================== API 路由 ====================

@app.route("/health")
def api_health():
    """健康检查"""
    return jsonify({"ok": True})


@app.route("/status")
def api_status():
    """引擎状态"""
    if not _engine_started:
        return jsonify({"running": False, "logged_in": False, "started": False})
    try:
        s = wa.get_monitor_status()
        s["started"] = True
        return jsonify(s)
    except Exception as e:
        return jsonify({"running": False, "logged_in": False, "started": True, "error": str(e)})


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
