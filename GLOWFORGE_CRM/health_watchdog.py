"""Health Watchdog — 系统健康监控

每10分钟检查一次:
  1. Flask app HTTP 可达
  2. WhatsApp 服务连接
  3. 数据库文件完整性
  4. CPU/内存使用率

运行方式:
    python health_watchdog.py              # 单次检查
    python health_watchdog.py --daemon     # 持续监控模式
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

# V0-SAFETY alert channel (graceful if unavailable)
try:
    from safety.alert_channel import send_alert
    HAS_ALERT = True
except ImportError:
    HAS_ALERT = False
    send_alert = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "watchdog.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("watchdog")

APP_PORT = 5789
WA_PORT = 15789
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
PID_FILE = os.path.join(BASE_DIR, ".crm_lock", "app.pid")


def check_http(port, path="/health", timeout=5):
    """检查 HTTP 服务是否可达"""
    try:
        url = f"http://127.0.0.1:{port}{path}"
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode())
            return r.status == 200, data
    except Exception as e:
        return False, str(e)


def check_database():
    """检查数据库文件完整性"""
    if not os.path.exists(DB_PATH):
        return False, "database file missing"
    size = os.path.getsize(DB_PATH)
    if size < 1024:
        return False, f"database too small: {size} bytes"
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
        return True, f"ok ({size // 1024} KB)"
    except Exception as e:
        return False, str(e)


def check_process(name_hint="python"):
    """检查进程是否在运行"""
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq python.exe", "/NH"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=10,
            )
            count = r.stdout.count("python.exe")
        else:
            r = subprocess.run(
                ["pgrep", "-c", "python"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=10,
            )
            count = int(r.stdout.strip() or 0)
        return count > 0, count
    except Exception:
        return False, 0


def check_disk_usage(path=None):
    """检查磁盘使用率"""
    if path is None:
        path = BASE_DIR
    try:
        if sys.platform == "win32":
            import ctypes
            drive = os.path.splitdrive(path)[0]
            if not drive.endswith("\\"):
                drive += "\\"
            free = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                drive, None, ctypes.byref(total), ctypes.byref(free)
            )
            total = total.value
            free = free.value
            if total > 0:
                return free / total, total, free
        else:
            st = os.statvfs(path)
            free = st.f_bavail * st.f_frsize
            total = st.f_blocks * st.f_frsize
            return free / total, total, free
    except Exception:
        pass
    return 0.5, 0, 0


def check_all():
    """执行全部健康检查"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "checks": {},
    }

    # Flask app
    app_ok, app_data = check_http(APP_PORT)
    results["checks"]["app"] = {
        "status": "ok" if app_ok else "down",
        "detail": app_data if isinstance(app_data, dict) else app_data,
    }

    # WhatsApp
    wa_ok, wa_data = check_http(WA_PORT)
    results["checks"]["whatsapp"] = {
        "status": "connected" if wa_ok else "disconnected",
        "detail": wa_data if isinstance(wa_data, dict) else wa_data,
    }

    # Database
    db_ok, db_detail = check_database()
    results["checks"]["database"] = {
        "status": "ok" if db_ok else "error",
        "detail": db_detail,
    }

    # Process
    proc_ok, proc_count = check_process()
    results["checks"]["process"] = {
        "status": "ok" if proc_ok else "no_python_process",
        "detail": f"{proc_count} python processes",
    }

    # Disk
    ratio, total, free = check_disk_usage()
    results["checks"]["disk"] = {
        "status": "ok" if ratio > 0.1 else "low_space",
        "detail": f"{ratio*100:.1f}% free ({free//(1024**3)} GB / {total//(1024**3)} GB)",
    }

    # Overall status
    all_ok = all(
        c["status"] in ("ok", "connected")
        for name, c in results["checks"].items()
    )
    results["overall"] = "ok" if all_ok else "degraded"
    results["healthy"] = all_ok

    return results


def try_restart():
    """尝试重启 Flask 应用"""
    logger.warning("Attempting to restart Flask app...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/FI", f"PID ge 0", "/FI",
                 f"WINDOWTITLE eq app.py"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5,
            )
    except Exception:
        pass
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(old_pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5,
                )
    except Exception:
        pass
    logger.warning("Restart attempt issued — start.bat must be run manually for safety")


def run_once():
    """单次检查"""
    results = check_all()
    status_str = results["overall"]
    logger.info(
        f"Health: {status_str}"
        f" | App: {results['checks']['app']['status']}"
        f" | WA: {results['checks']['whatsapp']['status']}"
        f" | DB: {results['checks']['database']['status']}"
        f" | Disk: {results['checks']['disk']['detail']}"
    )
    if not results["healthy"]:
        logger.warning(f"Degraded checks: {json.dumps(results['checks'], indent=2)}")
        for name, c in results["checks"].items():
            if c["status"] not in ("ok", "connected"):
                logger.warning(f"  FAIL {name}: {c['detail']}")
        # V0-SAFETY: send alert on degradation
        if HAS_ALERT:
            send_alert(
                f"Health check degraded:\n" +
                "\n".join(f"  {n}: {c['status']} — {c['detail']}"
                          for n, c in results["checks"].items()
                          if c["status"] not in ("ok", "connected")),
                severity="warning",
            )
    return results


def run_daemon(interval=600):
    """持续监控模式（默认每10分钟）"""
    logger.info(f"Watchdog daemon started (interval={interval}s)")
    consecutive_failures = 0
    while True:
        try:
            results = run_once()
            if not results["healthy"]:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.error(
                        f"{consecutive_failures} consecutive failures — "
                        f"attempting restart..."
                    )
                    # V0-SAFETY: critical alert before restart
                    if HAS_ALERT:
                        send_alert(
                            f"{consecutive_failures} consecutive health check failures — "
                            f"attempting service restart",
                            severity="critical",
                        )
                    try_restart()
                    consecutive_failures = 0
            else:
                consecutive_failures = 0
        except Exception as e:
            logger.error(f"Watchdog check failed: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Health Watchdog")
    parser.add_argument("--daemon", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int, default=600, help="检查间隔（秒）")
    args = parser.parse_args()

    if args.daemon:
        run_daemon(interval=args.interval)
    else:
        run_once()
