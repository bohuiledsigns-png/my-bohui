"""动作执行器 — 将决策翻译为系统操作"""

import sqlite3
import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ======================== 动作执行日志 ========================

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_action_log():
    """确保动作日志表存在"""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            action_label TEXT DEFAULT '',
            status TEXT DEFAULT 'completed',
            result TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.commit()
    conn.close()


def log_action(customer_id, action, status="completed", result="", detail=""):
    """记录执行的动作"""
    _ensure_action_log()
    conn = _get_db()
    conn.execute(
        "INSERT INTO lead_action_log (customer_id, action, action_label, status, result, detail) VALUES (?,?,?,?,?,?)",
        (customer_id, action, action, status, result, detail)
    )
    conn.commit()
    conn.close()


def get_action_history(customer_id, limit=20):
    """获取客户动作历史"""
    _ensure_action_log()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM lead_action_log WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================== 动作执行器 ========================
# 注意: action_router 不直接 import app.py 或 whatsapp_engine
# 以避免循环引用。实际执行通过回调函数注入。
# 这些回调在 app.py 启动时注册。

_callbacks = {}


def register_action(action_name, callback):
    """注册一个动作的执行回调

    参数:
        action_name: 动作名称 (如 "SEND_QUOTE")
        callback: 函数签名 fn(customer_id, context) → dict
    """
    _callbacks[action_name] = callback


def execute_action(action_name, customer_id, context=None):
    """执行一个动作

    参数:
        action_name: 动作名称
        customer_id: 客户ID
        context: dict, 包含执行所需上下文 (如 chat_name, reply_text 等)

    返回:
        dict: {ok, action, result, detail}
    """
    ctx = context or {}

    # 记录执行
    _ensure_action_log()

    # 找回调
    callback = _callbacks.get(action_name)
    if callback:
        try:
            result = callback(customer_id, ctx)
            status = "completed" if result.get("ok", True) else "failed"
            log_action(customer_id, action_name, status, str(result.get("result", "")), result.get("detail", ""))
            return {"ok": status == "completed", "action": action_name, "result": result, "detail": result.get("detail", "")}
        except Exception as e:
            log_action(customer_id, action_name, "error", "", str(e))
            return {"ok": False, "action": action_name, "error": str(e)}

    # 没有回调 — 只记录（比如 ROUTINE_REPLY 这样的无操作动作）
    log_action(customer_id, action_name, "logged", "no_callback", "动作无回调，仅记录")
    return {"ok": True, "action": action_name, "result": "logged", "detail": "无操作动作"}


def get_registered_actions():
    """列出已注册的动作列表"""
    return {k: v.__name__ if hasattr(v, '__name__') else str(v) for k, v in _callbacks.items()}
