"""Safety Dashboard — 安全指标 Flask Blueprint

提供 V0-SAFETY 各层的 REST API:
  GET /api/v0/safety/health     — 聚合健康状态
  GET /api/v0/safety/backups    — 最近备份列表
  GET /api/v0/safety/audit      — 消息审计日志
  GET /api/v0/safety/shadow     — 影子运行记录
  GET /api/v0/safety/alerts     — 告警记录
"""
import json
import logging
import os
from datetime import datetime

from flask import Blueprint, jsonify

logger = logging.getLogger("glowforge.safety")

bp = Blueprint("safety", __name__, url_prefix="/api/v0/safety")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
LOG_DIR = os.path.join(BASE_DIR, "logs")


def _read_log_lines(path, max_lines=50):
    """读取日志文件末尾最多 max_lines 行"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-max_lines:] if l.strip()]
    except (OSError, UnicodeDecodeError):
        return []


@bp.route("/health", methods=["GET"])
def safety_health():
    """聚合健康状态"""
    # Check health endpoint if reachable
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:5789/health", timeout=3) as r:
            health_data = json.loads(r.read().decode())
    except Exception as e:
        health_data = {"error": str(e)}

    # Disk
    try:
        st = os.statvfs(BASE_DIR)
        free_ratio = st.f_bavail / st.f_blocks if st.f_blocks else 0
        free_gb = st.f_bavail * st.f_frsize / (1024**3)
    except Exception:
        free_ratio = 0
        free_gb = 0

    # Database size
    db_path = os.path.join(BASE_DIR, "crm_data.db")
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    # Recent backup
    latest_backup = None
    if os.path.isdir(BACKUP_DIR):
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith("crm_data-")],
            reverse=True,
        )
        if backups:
            latest_backup = backups[0]

    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "app_health": health_data.get("status") if isinstance(health_data, dict) else "unknown",
        "database": {
            "size_bytes": db_size,
            "size_mb": round(db_size / (1024**2), 1),
        },
        "disk": {
            "free_ratio": round(free_ratio, 2),
            "free_gb": round(free_gb, 1),
        },
        "latest_backup": latest_backup,
    })


@bp.route("/backups", methods=["GET"])
def list_backups():
    """列出最近备份"""
    if not os.path.isdir(BACKUP_DIR):
        return jsonify({"backups": []})

    files = sorted(
        [f for f in os.listdir(BACKUP_DIR)
         if f.startswith("crm_data-") or f.endswith(".db") or f.endswith(".gz")],
        reverse=True,
    )[:20]

    backups = []
    for fname in files:
        fpath = os.path.join(BACKUP_DIR, fname)
        try:
            size = os.path.getsize(fpath)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()
        except OSError:
            size = 0
            mtime = ""
        backups.append({
            "file": fname,
            "size_bytes": size,
            "size_mb": round(size / (1024**2), 2),
            "modified": mtime,
        })

    return jsonify({"backups": backups})


@bp.route("/audit", methods=["GET"])
def audit_log():
    """消息审计日志"""
    lines = _read_log_lines(os.path.join(LOG_DIR, "message_audit.log"), max_lines=50)
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"raw": line})

    return jsonify({
        "total": len(entries),
        "entries": entries[-50:],
    })


@bp.route("/shadow", methods=["GET"])
def shadow_history():
    """影子运行记录"""
    lines = _read_log_lines(os.path.join(LOG_DIR, "shadow_run.log"), max_lines=30)
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return jsonify({
        "total": len(entries),
        "entries": entries[-20:],
    })


@bp.route("/alerts", methods=["GET"])
def alert_history():
    """告警记录"""
    lines = _read_log_lines(os.path.join(LOG_DIR, "alert.log"), max_lines=50)
    return jsonify({
        "total": len(lines),
        "entries": lines[-50:],
    })
