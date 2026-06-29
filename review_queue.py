"""AI Reply Review Queue — 回复审核队列

AI 自动回复不再直接发出，而是进入审核队列。
管理员可在面板上: 批准 / 编辑后批准 / 驳回 / 忽略

超时自动发送（默认 30 分钟，管理员单独配置）。
"""
import json
import os
import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger("review_queue")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(BASE_DIR, "data", "review_queue.json")

# 默认超时（秒）
DEFAULT_AUTO_SEND_TIMEOUT = 30 * 60  # 30 分钟

_lock = threading.Lock()
_timer = None


def _load():
    """加载持久化审核队列"""
    if not os.path.exists(QUEUE_PATH):
        return []
    try:
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(queue):
    """持久化审核队列"""
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    tmp = QUEUE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE_PATH)


def enqueue(customer_id, customer_name, reply_en, reply_cn,
            original_message="", auto_send_timeout=DEFAULT_AUTO_SEND_TIMEOUT):
    """将待审核回复加入队列"""
    entry = {
        "id": f"REV-{int(time.time() * 1000)}-{hash(customer_name) % 10000:04d}",
        "customer_id": customer_id,
        "customer_name": customer_name,
        "reply_en": reply_en,
        "reply_cn": reply_cn,
        "original_message": original_message,
        "status": "pending",  # pending | approved | rejected | auto_sent
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now().timestamp() + auto_send_timeout),
        "edited_en": None,
        "edited_cn": None,
        "reviewed_by": None,
        "reviewed_at": None,
    }
    with _lock:
        queue = _load()
        # 对同一客户去重（保留最新的）
        queue = [q for q in queue
                 if not (q["customer_id"] == customer_id and q["status"] == "pending")]
        queue.append(entry)
        _save(queue)
    logger.info(f"[ReviewQueue] enqueued {entry['id']} for {customer_name}")
    return entry


def list_pending():
    """列出所有待审核回复"""
    with _lock:
        queue = _load()
        return [q for q in queue if q["status"] == "pending"]


def list_all(limit=50):
    """列出所有审核记录（最近limit条）"""
    with _lock:
        queue = _load()
        queue.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return queue[:limit]


def approve(review_id, reviewer="admin", edit_en=None, edit_cn=None):
    """批准回复（可选编辑后批准）"""
    with _lock:
        queue = _load()
        for entry in queue:
            if entry["id"] == review_id and entry["status"] == "pending":
                entry["status"] = "approved"
                entry["reviewed_by"] = reviewer
                entry["reviewed_at"] = datetime.now().isoformat()
                if edit_en:
                    entry["edited_en"] = edit_en
                if edit_cn:
                    entry["edited_cn"] = edit_cn
                _save(queue)
                logger.info(f"[ReviewQueue] approved {review_id} by {reviewer}")
                return entry
    return None


def reject(review_id, reviewer="admin"):
    """驳回回复"""
    with _lock:
        queue = _load()
        for entry in queue:
            if entry["id"] == review_id and entry["status"] == "pending":
                entry["status"] = "rejected"
                entry["reviewed_by"] = reviewer
                entry["reviewed_at"] = datetime.now().isoformat()
                _save(queue)
                logger.info(f"[ReviewQueue] rejected {review_id} by {reviewer}")
                return entry
    return None


def get_expired(now=None):
    """获取已过期的待审核条目"""
    now = now or time.time()
    with _lock:
        queue = _load()
        return [q for q in queue
                if q["status"] == "pending" and q.get("expires_at", 0) < now]


def mark_auto_sent(review_id):
    """标记为超时自动发送"""
    with _lock:
        queue = _load()
        for entry in queue:
            if entry["id"] == review_id and entry["status"] == "pending":
                entry["status"] = "auto_sent"
                entry["reviewed_at"] = datetime.now().isoformat()
                _save(queue)
                return entry
    return None


def pending_count():
    """待审核数量"""
    with _lock:
        queue = _load()
        return sum(1 for q in queue if q["status"] == "pending")


def cleanup_old(days=7):
    """清理超过N天的已处理记录"""
    with _lock:
        queue = _load()
        cutoff = (datetime.now().timestamp() - days * 86400)
        queue = [q for q in queue
                 if q["status"] == "pending" or
                 (q.get("reviewed_at", "") and
                  datetime.strptime(q["reviewed_at"][:19],
                                    "%Y-%m-%dT%H:%M:%S").timestamp() > cutoff)]
        _save(queue)
