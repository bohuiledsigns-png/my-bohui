"""Structured Logging — 结构化日志配置

单次初始化，同时写入:
  - logs/app.log     (轮转, 10MB×5, JSON格式)
  - logs/error.log   (WARNING+, 便于快速定位问题)
  - console          (人类可读格式)

用法:
    from safety.log_setup import init_logging
    init_logging()
    logger = logging.getLogger("glowforge.module")
"""
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime


class JsonFormatter(logging.Formatter):
    """输出 JSON 格式日志，便于机器解析"""

    def format(self, record):
        obj = {
            "ts": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            obj["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_fields"):
            obj.update(record.extra_fields)
        return json.dumps(obj, ensure_ascii=False)


_CONFIGURED = False


def init_logging(log_dir=None, level=None):
    """初始化结构化日志（幂等，多次调用不重复配置）

    参数:
        log_dir: 日志目录，默认 BASE_DIR/logs/
        level:   日志级别，默认从环境变量 LOG_LEVEL 读取，INFO 兜底
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if log_dir is None:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs",
        )
    os.makedirs(log_dir, exist_ok=True)

    if level is None:
        level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

    # ── 根 logger ──
    root = logging.getLogger()
    root.setLevel(level)

    # 清除已有 handlers（避免重复配置）
    root.handlers.clear()

    # ── 全量日志 (JSON 轮转) ──
    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setLevel(level)
    app_handler.setFormatter(JsonFormatter())
    root.addHandler(app_handler)

    # ── 错误日志 (WARNING+, JSON) ──
    err_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(JsonFormatter())
    root.addHandler(err_handler)

    # ── 控制台 (人类可读) ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(console)

    logging.getLogger("glowforge").info(
        "Logging initialized", extra={"extra_fields": {"log_dir": log_dir, "level": logging.getLevelName(level)}}
    )
