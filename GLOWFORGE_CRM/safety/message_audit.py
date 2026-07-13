"""Message Audit — 出站消息审计日志

记录每条出站消息的审核结果，保留最近1000条环形缓冲区。
"""
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime

logger = logging.getLogger("glowforge.message_audit")

_AUDIT_RING = deque(maxlen=1000)
_lock = threading.Lock()


def log_outbound(customer_id, message_text, gate_result, status="sent"):
    """记录出站消息

    参数:
        customer_id: 客户ID
        message_text: 消息内容（前100字符）
        gate_result: content_gate 的返回结果
        status: sent | blocked | modified | approved | auto_sent
    """
    entry = {
        "ts": datetime.now().isoformat(),
        "customer_id": customer_id,
        "preview": message_text[:100],
        "gate_passed": gate_result.get("passed", False),
        "gate_severity": gate_result.get("severity", ""),
        "blocked_count": len(gate_result.get("blocked_rules", [])),
        "gate_time_ms": gate_result.get("gate_time_ms", 0),
        "status": status,
    }
    with _lock:
        _AUDIT_RING.append(entry)

    # Also persist to audit log file
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)
    try:
        with open(os.path.join(log_dir, "message_audit.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_recent_audit_log(limit=50):
    """获取最近审计记录"""
    with _lock:
        return list(_AUDIT_RING)[-limit:]


def get_audit_summary():
    """获取审计摘要"""
    with _lock:
        total = len(_AUDIT_RING)
        blocked = sum(1 for e in _AUDIT_RING if e["status"] == "blocked")
        sent = sum(1 for e in _AUDIT_RING if e["status"] == "sent")
        return {
            "total": total,
            "sent": sent,
            "blocked": blocked,
            "block_rate": round(blocked / total * 100, 1) if total else 0,
        }
