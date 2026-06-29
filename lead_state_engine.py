"""客户状态机引擎 — 跟踪每个客户的成交阶段"""

import sqlite3
import os
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ======================== 状态定义 ========================
# 每个客户在销售流程中的精确位置
LEAD_STATES = {
    "NEW": "刚进来，还没表达需求",
    "INTERESTED": "有兴趣（问过产品/看过）",
    "REQUESTED_PRICE": "问过价格",
    "QUOTED": "已报价",
    "NEGOTIATING": "在比价/犹豫/谈条件",
    "HOT": "强购买信号（准备下单）",
    "COLD": "沉默/流失风险（超过72小时未回复）",
    "CLOSED_WON": "成交",
    "CLOSED_LOST": "流失",
}

# 状态流转白名单（from_state → [to_state, ...]）
_ALLOWED_TRANSITIONS = {
    "NEW": ["INTERESTED", "REQUESTED_PRICE", "NEGOTIATING", "COLD", "CLOSED_LOST"],
    "INTERESTED": ["REQUESTED_PRICE", "NEGOTIATING", "HOT", "COLD", "CLOSED_LOST"],
    "REQUESTED_PRICE": ["QUOTED", "NEGOTIATING", "COLD", "CLOSED_LOST"],
    "QUOTED": ["NEGOTIATING", "HOT", "COLD", "CLOSED_LOST"],
    "NEGOTIATING": ["HOT", "QUOTED", "COLD", "CLOSED_LOST", "CLOSED_WON"],
    "HOT": ["NEGOTIATING", "CLOSED_WON", "CLOSED_LOST"],
    "COLD": ["INTERESTED", "REQUESTED_PRICE", "CLOSED_LOST"],
    "CLOSED_WON": [],
    "CLOSED_LOST": [],
}

# 售前状态（可以继续推进）
_ACTIVE_STATES = {"NEW", "INTERESTED", "REQUESTED_PRICE", "QUOTED", "NEGOTIATING", "HOT", "COLD"}


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ======================== 数据库操作 ========================

def _ensure_state_field():
    """确保 customers 表有 lead_state 字段"""
    conn = _get_db()
    try:
        conn.execute("ALTER TABLE customers ADD COLUMN lead_state TEXT DEFAULT 'NEW'")
    except:
        pass
    conn.close()


def _ensure_state_log_table():
    """确保 state_log 表存在"""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_state_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            trigger_source TEXT DEFAULT '',     -- 'intent' / 'manual' / 'timeout'
            trigger_detail TEXT DEFAULT '',      -- 触发原因
            intent TEXT DEFAULT '',              -- 触发的意图
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.commit()
    conn.close()


def get_lead_state(customer_id):
    """读取客户当前状态"""
    _ensure_state_field()
    conn = _get_db()
    row = conn.execute("SELECT lead_state FROM customers WHERE id=?", (customer_id,)).fetchone()
    conn.close()
    if row and row["lead_state"]:
        return row["lead_state"]
    return "NEW"


def set_lead_state(customer_id, state):
    """直接设置客户状态（手动操作用）"""
    _ensure_state_field()
    conn = _get_db()
    conn.execute("UPDATE customers SET lead_state=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (state, customer_id))
    conn.commit()
    conn.close()


def log_state_transition(customer_id, from_state, to_state, trigger_source="", trigger_detail="", intent=""):
    """记录状态变更日志"""
    _ensure_state_log_table()
    conn = _get_db()
    conn.execute(
        "INSERT INTO lead_state_log (customer_id, from_state, to_state, trigger_source, trigger_detail, intent) VALUES (?,?,?,?,?,?)",
        (customer_id, from_state, to_state, trigger_source, trigger_detail, intent)
    )
    conn.commit()
    conn.close()


def get_state_history(customer_id, limit=20):
    """获取客户状态变更历史"""
    _ensure_state_log_table()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM lead_state_log WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================== 意图 → 状态映射 ========================

_INTENT_STATE_MAP = {
    "询价": "REQUESTED_PRICE",
    "比价": "NEGOTIATING",
    "问工艺": "INTERESTED",
    "要样品": "INTERESTED",
    "下单": "HOT",
    "售后": "QUOTED",      # 已有客户，保持报价阶段
    "合作": "INTERESTED",
    "要目录": "INTERESTED",
    "跟进": None,           # 不改变状态
    "其他": None,           # 不改变状态
}


def _check_no_reply_timeout(customer_id):
    """检查客户是否超过72小时未回复"""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT created_at FROM messages WHERE customer_id=? AND direction='received' ORDER BY created_at DESC LIMIT 1",
            (customer_id,)
        ).fetchone()
        conn.close()
        if not row:
            return False
        last_reply = datetime.strptime(row["created_at"][:19], "%Y-%m-%d %H:%M:%S")
        return datetime.now() - last_reply > timedelta(hours=72)
    except:
        return False


def update_lead_state(customer_id, intent, trigger_detail=""):
    """根据意图更新客户状态 — 核心函数

    参数:
        customer_id: 客户ID
        intent: 从analyze_customer_message()返回的意图
        trigger_detail: 触发详情（如客户消息摘要）

    返回:
        dict: {from_state, to_state, transitioned, reason}
    """
    _ensure_state_field()

    current = get_lead_state(customer_id)
    target_state = _INTENT_STATE_MAP.get(intent)

    # 意图不触发状态变更
    if target_state is None:
        # 但检查是否超时沉默
        if current in _ACTIVE_STATES and _check_no_reply_timeout(customer_id):
            if current != "COLD":
                log_state_transition(customer_id, current, "COLD",
                                     trigger_source="timeout",
                                     trigger_detail="超过72小时未回复",
                                     intent=intent)
                set_lead_state(customer_id, "COLD")
                return {"from_state": current, "to_state": "COLD", "transitioned": True, "reason": "超时沉默"}
        return {"from_state": current, "to_state": current, "transitioned": False, "reason": "意图不触发状态变更"}

    # 检查是否在允许的转换白名单中
    allowed = _ALLOWED_TRANSITIONS.get(current, [])
    if target_state in allowed:
        log_state_transition(customer_id, current, target_state,
                             trigger_source="intent",
                             trigger_detail=trigger_detail,
                             intent=intent)
        set_lead_state(customer_id, target_state)
        return {"from_state": current, "to_state": target_state, "transitioned": True, "reason": f"意图={intent}"}

    # 特例：如果客户是NEW但意图是请求报价，NEW→REQUESTED_PRICE
    if current == "NEW" and target_state == "REQUESTED_PRICE":
        # 先走 INTERESTED 再跳 REQUESTED_PRICE
        log_state_transition(customer_id, "NEW", "INTERESTED",
                             trigger_source="intent", trigger_detail=f"{trigger_detail} (中间态)", intent=intent)
        log_state_transition(customer_id, "INTERESTED", "REQUESTED_PRICE",
                             trigger_source="intent", trigger_detail=trigger_detail, intent=intent)
        set_lead_state(customer_id, "REQUESTED_PRICE")
        return {"from_state": "NEW", "to_state": "REQUESTED_PRICE", "transitioned": True, "reason": f"意图={intent} (经INTERESTED跳转)"}

    # 不在白名单中 → 不转换
    return {"from_state": current, "to_state": current, "transitioned": False, "reason": f"{current}→{target_state} 不在白名单"}


def init_customer_state(customer_id):
    """新客户初始化状态"""
    _ensure_state_field()
    set_lead_state(customer_id, "NEW")
    log_state_transition(customer_id, "", "NEW",
                         trigger_source="manual",
                         trigger_detail="新客户创建")
    return "NEW"


def batch_check_timeout():
    """批量检查所有活跃客户是否超时（定时任务用）"""
    _ensure_state_field()
    conn = _get_db()
    active = conn.execute(
        "SELECT id, name FROM customers WHERE lead_state IN ('NEW','INTERESTED','REQUESTED_PRICE','QUOTED','NEGOTIATING','HOT')"
    ).fetchall()
    conn.close()

    results = []
    now = datetime.now()
    for row in active:
        cid = row["id"]
        try:
            c = _get_db()
            last = c.execute(
                "SELECT created_at FROM messages WHERE customer_id=? AND direction='received' ORDER BY created_at DESC LIMIT 1",
                (cid,)
            ).fetchone()
            c.close()
            if last:
                last_time = datetime.strptime(last["created_at"][:19], "%Y-%m-%d %H:%M:%S")
                if now - last_time > timedelta(hours=72):
                    set_lead_state(cid, "COLD")
                    log_state_transition(cid, row["lead_state"], "COLD",
                                         trigger_source="timeout",
                                         trigger_detail="批量超时检查")
                    results.append({"customer_id": cid, "name": row["name"], "transitioned": True})
        except:
            continue
    return results
