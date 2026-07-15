"""GLOWFORGE WhatsApp Engine — Playwright异步版 (v3 稳定版)
直接操作WhatsApp Web DOM，7×24小时自动运行
专用事件循环线程，无多线程冲突
v3: 使用 subprocess + CDP 替代 launch_persistent_context，大幅提升稳定性
"""
import os
import re
import sys
import uuid
import time
import random
import queue
import json
import threading
import asyncio
import subprocess
import socket

# ==================== 配置 ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whatsapp_session")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "storage_state.json")
PROFILE_DIR = os.path.join(DATA_DIR, "persistent_profile")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")


def _log(msg):
    """写入日志文件（避免gbk编码问题）"""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
    # 同时打印到控制台（安全编码）
    try:
        safe = msg.encode("utf-8", errors="replace").decode("utf-8")
        print(safe)
    except Exception:
        pass

# ==================== 限速器(防封) ====================
class RateLimiter:
    def __init__(self, max_per_hour=20, min_interval=15):
        self.max_per_hour = max_per_hour
        self.min_interval = min_interval
        self.timestamps = []
        self.lock = threading.Lock()

    def can_send(self):
        with self.lock:
            now = time.time()
            self.timestamps = [t for t in self.timestamps if now - t < 3600]
            if len(self.timestamps) >= self.max_per_hour:
                return False, f"已达每小时{self.max_per_hour}条上限"
            if self.timestamps and now - self.timestamps[-1] < self.min_interval:
                wait = int(self.min_interval - (now - self.timestamps[-1]))
                return False, f"请等待{wait}秒"
            self.timestamps.append(now)
            return True, "ok"

rate_limiter = RateLimiter(max_per_hour=15, min_interval=30)


# ==================== 异步Playwright引擎 ====================
# 设计: 单线程事件循环 + 命令队列 + 回调
# 所有Playwright调用都在同一个线程执行

_cmd_queue = queue.Queue()         # 外部→引擎的命令
_cmd_results = {}                   # 命令结果(id -> result)
_cmd_events = {}                    # 命令完成信号(id -> threading.Event)
_cmd_counter = 0
_cmd_lock = threading.Lock()

_on_message_callback = None         # 收到新消息时的回调
_running = threading.Event()
_running.set()                     # 默认运行

_page_ready = threading.Event()     # 页面加载完成信号
_page = None                        # 全局page引用
_browser_context = None             # 持久化context

_loop = None
_loop_thread = None

# ============ v3 稳定版：subprocess + CDP + 心跳 ============
_chrome_subprocess = None           # Chrome 子进程 (Popen)
_last_heartbeat = 0.0               # 上次成功 JS evaluate 的时间戳
_needs_reauth = False               # Profile 损坏，需要重新扫码
_CDP_PORT = 9223                    # Chrome 远程调试端口（避开用户可能的 9222）
_CHROME_RESTART_DELAY = 3.0         # Chrome崩溃后等待秒数（极速恢复）

# 启动次数统计（用于日志）
_launch_count = 0
_heartbeat_lock = threading.Lock()


def _update_heartbeat():
    """更新心跳时间戳（线程安全）"""
    with _heartbeat_lock:
        global _last_heartbeat
        _last_heartbeat = time.time()


def _get_heartbeat_ago():
    """获取上次心跳距今秒数"""
    with _heartbeat_lock:
        if _last_heartbeat <= 0:
            return -1
        return time.time() - _last_heartbeat


def _gen_cmd_id():
    global _cmd_counter
    with _cmd_lock:
        _cmd_counter += 1
        return f"cmd_{_cmd_counter}_{uuid.uuid4().hex[:4]}"


# ==================== v3 稳定版：Chrome 进程管理 ====================

def _find_chrome_path():
    """查找 Chrome 可执行文件路径"""
    try:
        import shutil
        # Windows 常见安装路径
        candidates = [
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        # Playwright 自带的 Chromium
        try:
            from playwright._impl._path_utils import get_driver_dir
            driver_dir = get_driver_dir()
            for fname in ("chrome.exe", "chromium.exe"):
                fp = os.path.join(driver_dir, "chromium", fname)
                if os.path.exists(fp):
                    return fp
        except Exception:
            pass
        # PATH 搜索
        result = shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")
        if result:
            return result
    except Exception:
        pass
    return None


def _kill_chrome_on_port(port):
    """杀死占用指定端口的 Chrome 进程"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True, capture_output=True, text=True, timeout=10
        )
        pids = set()
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit():
                    pids.add(pid)
        for pid in pids:
            try:
                subprocess.run(['taskkill', '/F', '/PID', pid],
                               capture_output=True, timeout=10)
                _log(f"[ChromeMgmt] 已杀死占用端口 {port} 的进程 PID={pid}")
            except Exception:
                pass
        if pids:
            time.sleep(1)  # 等进程完全退出
    except Exception:
        pass


def _kill_all_chrome_for_profile():
    """杀死所有使用当前 profile 目录的 Chrome 进程（防止锁文件冲突）"""
    try:
        result = subprocess.run(
            'tasklist /FO CSV /NH /FI "IMAGENAME eq chrome.exe"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        if PROFILE_DIR.lower() in result.stdout.lower():
            # 有 Chrome 使用该 profile，全杀
            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'],
                           capture_output=True, timeout=10)
            time.sleep(2)
            _log("[ChromeMgmt] 已杀死所有 Chrome 进程（释放 profile 锁）")
    except Exception:
        pass


def _get_chrome_cmd(port=None):
    """构造 Chrome 启动命令行"""
    if port is None:
        port = _CDP_PORT
    chrome_path = _find_chrome_path()
    if not chrome_path:
        return None
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-automation",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--disable-features=VizDisplayCompositor",
        "--no-sandbox",
        "--disable-background-networking",
        "--disable-sync",
    ]
    return args


def _start_chrome_process():
    """启动 Chrome 子进程，返回 Popen 对象"""
    global _chrome_subprocess
    cmd = _get_chrome_cmd()
    if not cmd:
        raise Exception("找不到 Chrome 可执行文件，请确认已安装 Google Chrome")

    _log(f"[ChromeMgmt] 启动 Chrome: {cmd[0]}")
    # keep proxy env for internet (needed for WhatsApp in China),
    # but add NO_PROXY so DevTools/localhost bypass the proxy
    _chrome_env = os.environ.copy()
    for _k in ("NO_PROXY", "no_proxy"):
        _chrome_env.setdefault(_k, "localhost,127.0.0.1")
    _chrome_subprocess = subprocess.Popen(
        cmd, env=_chrome_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _log(f"[ChromeMgmt] Chrome PID={_chrome_subprocess.pid}")

    # 等待 CDP 端口就绪 + DevTools 端点正常响应（最多 30 秒）
    import urllib.request as _ur
    for i in range(30):
        if not _running.is_set():
            raise Exception("引擎已停止")
        if _chrome_subprocess.poll() is not None:
            raise Exception(f"Chrome 进程已退出 (exit={_chrome_subprocess.returncode})")

        # 第 1 步：等 TCP 端口就绪
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        port_ready = False
        try:
            if s.connect_ex(('127.0.0.1', _CDP_PORT)) == 0:
                port_ready = True
            s.close()
        except Exception:
            s.close()
        if not port_ready:
            time.sleep(1)
            continue

        # 第 2 步：等 DevTools HTTP 端点返回 200（bypass proxy）
        try:
            _no_proxy = _ur.ProxyHandler({})
            _opener = _ur.build_opener(_no_proxy)
            with _opener.open(f"http://127.0.0.1:{_CDP_PORT}/json/version", timeout=3) as resp:
                if resp.status == 200:
                    version_info = resp.read().decode()
                    _log(f"[ChromeMgmt] DevTools 已就绪 (第{i+1}次尝试)")
                    return _chrome_subprocess
        except Exception:
            pass
        time.sleep(1)

    raise Exception(f"Chrome DevTools 端口 {_CDP_PORT} 等待超时（30秒）")


def _get_devtools_ws_url():
    """从 Chrome DevTools 接口获取 WebSocket 连接 URL

    直接传 HTTP 地址给 Playwright connect_over_cdp 在某些版本有 bug
    （Chrome 149 + Playwright 1.58），返回 400。
    手动获取 ws:// URL 后传给 Playwright 可以绕过该 bug。
    """
    import urllib.request as _ur
    _no_proxy = _ur.ProxyHandler({})
    _opener = _ur.build_opener(_no_proxy)
    for i in range(10):
        try:
            with _opener.open(f"http://127.0.0.1:{_CDP_PORT}/json/version", timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    ws = data.get("webSocketDebuggerUrl")
                    if ws:
                        _log(f"[ChromeMgmt] DevTools WS: {ws}")
                        return ws
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _stop_chrome_process():
    """停止 Chrome 子进程"""
    global _chrome_subprocess
    if _chrome_subprocess is not None:
        try:
            if _chrome_subprocess.poll() is None:
                _chrome_subprocess.terminate()
                _chrome_subprocess.wait(timeout=5)
        except Exception:
            try:
                _chrome_subprocess.kill()
            except Exception:
                pass
        _chrome_subprocess = None
        _log("[ChromeMgmt] Chrome 子进程已停止")


async def _execute_cmd(cmd, page):
    """执行一条命令，返回结果"""
    cmd_type = cmd.get("type")
    try:
        if cmd_type == "send_text":
            contact_name = cmd.get("contact_name")
            text = cmd.get("text", "")
            if contact_name:
                await _switch_chat(page, contact_name)
            # 多种输入框选择器
            input_box = None
            input_selectors = [
                'div[aria-placeholder="Type a message"]',
                'div[aria-placeholder="输入消息"]',
                'div[title="Type a message"]',
                'footer div[contenteditable="true"]',
                'div[contenteditable="true"][role="textbox"]',
            ]
            for sel in input_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    input_box = loc
                    break
            if not input_box:
                return {"error": "找不到输入框"}
            await input_box.click(timeout=5000)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await input_box.fill(text)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            return {"ok": True}

        elif cmd_type == "send_file":
            contact_name = cmd.get("contact_name")
            file_path = cmd.get("file_path", "")
            is_image = cmd.get("is_image", False)
            if contact_name:
                await _switch_chat(page, contact_name)
            async with page.expect_file_chooser() as fc_info:
                attach = page.locator('span[data-icon="plus"]').first
                if await attach.count() == 0:
                    attach = page.locator('div[aria-label="Attach"]').first
                await attach.click()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                if is_image:
                    item = page.locator('li:has-text("Photos")').first
                else:
                    item = page.locator('li:has-text("Document")').first
                if await item.count() > 0:
                    await item.click()
            file_chooser = await fc_info.value
            if file_chooser:
                await file_chooser.set_files(file_path, timeout=30000)
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            await asyncio.sleep(max(5, min(int(size_mb * 2), 60)))
            send_btn = page.locator('span[data-icon="send"]').first
            if await send_btn.count() > 0:
                await send_btn.click()
            else:
                await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            return {"ok": True}

        elif cmd_type == "read_messages":
            msgs = await _read_chat_messages(page, limit=5)
            return {"messages": msgs, "text": _format_messages(msgs)}

        elif cmd_type == "switch_chat":
            await _switch_chat(page, cmd.get("contact_name", ""))
            return {"ok": True}

        elif cmd_type == "get_unread":
            names = await _find_unread_chats(page)
            return {"unread": names}

        elif cmd_type == "check_logged_in":
            try:
                await page.wait_for_selector(
                    'div[aria-label="Chat list"], div[aria-label="聊天列表"], '
                    'div[aria-label*="chat" i], div[aria-label*="Chat" i], '
                    '[data-testid="chat-list"]',
                    timeout=15000)
                return {"logged_in": True}
            except:
                return {"logged_in": False}

        elif cmd_type == "get_status":
            try:
                await page.evaluate("1")
                _update_heartbeat()
                # 非阻塞检查：用JS瞬间查询DOM，不用wait_for_selector
                logged = await page.evaluate("""() => {
                    const selectors = [
                        'div[aria-label="Chat list"]',
                        'div[aria-label="聊天列表"]',
                        '[data-testid="chat-list"]'
                    ];
                    for (const sel of selectors) {
                        if (document.querySelector(sel)) return true;
                    }
                    return false;
                }""")
                return {"alive": True, "logged_in": logged}
            except:
                return {"alive": False, "logged_in": False}

        elif cmd_type == "refresh_page":
            try:
                await page.reload(timeout=60000)
                await asyncio.sleep(5)
                return {"ok": True}
            except Exception as e:
                return {"error": f"刷新失败: {e}"}

    except Exception as e:
        return {"error": str(e)}


async def _find_unread_chats(page):
    """找到所有有未读消息的聊天"""
    unread = []
    try:
        badges = page.locator('[data-testid="icon-unread-count"]')
        count = await badges.count()
        for i in range(count):
            try:
                name = await badges.nth(i).evaluate("""el => {
                    const row = el.closest('[role="row"]');
                    if (!row) return null;
                    const spans = row.querySelectorAll('span[dir="auto"]');
                    return spans.length > 0 ? spans[0].innerText : null;
                }""")
                if name and name not in unread:
                    unread.append(name)
            except:
                pass
    except:
        pass
    return unread


async def _switch_chat(page, contact_name):
    """切换到指定聊天——先搜聊天列表，搜不到就不切换，绝不乱点"""
    if not contact_name:
        return

    # 尝试多种匹配：全名、手机号、部分匹配
    def name_matches(row_text, target):
        if not row_text or not target:
            return False
        row_lower = row_text.lower().strip()
        target_lower = target.lower().strip()
        if target_lower == row_lower:
            return True
        if target_lower in row_lower or row_lower in target_lower:
            return True
        return False

    # ===== 方法1: 直接从聊天列表查找 =====
    try:
        chat_items = page.locator('[role="row"]')
        count = await chat_items.count()
        for i in range(count):
            try:
                text = await chat_items.nth(i).inner_text()
                if name_matches(text, contact_name):
                    await chat_items.nth(i).click(timeout=5000)
                    await asyncio.sleep(1.5)
                    _log(f"[SwitchChat] 列表匹配→已切换到: {contact_name}")
                    return
            except:
                pass
    except Exception as e:
        _log(f"[SwitchChat] 列表扫描失败: {e}")

    # ===== 方法2: 用搜索框 =====
    search_selectors = [
        'div[aria-label="Search input textbox"]',
        'div[aria-label="搜索输入框"]',
        'div[title="Search input textbox"]',
        'div[contenteditable="true"][aria-label*="Search" i]',
        'div[role="textbox"][aria-label*="Search" i]',
    ]
    search = None
    for sel in search_selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0:
                search = loc
                break
        except:
            pass

    if not search:
        try:
            btn = page.locator('button[aria-label*="Search" i], button[aria-label*="搜索" i]').first
            if await btn.count() > 0:
                await btn.click(timeout=5000)
                await asyncio.sleep(1)
                for sel in search_selectors:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        search = loc
                        break
        except:
            pass

    if search:
        try:
            await search.click(timeout=5000)
            await asyncio.sleep(0.5)
            await search.fill(contact_name)
            await asyncio.sleep(2)
            rows = page.locator('[role="row"]')
            for i in range(await rows.count()):
                try:
                    text = await rows.nth(i).inner_text()
                    if name_matches(text, contact_name):
                        await rows.nth(i).click(timeout=5000)
                        await asyncio.sleep(1.5)
                        _log(f"[SwitchChat] 搜索→已切换到: {contact_name}")
                        return
                except:
                    pass
        except Exception as e:
            _log(f"[SwitchChat] 搜索操作失败: {e}")

    # ===== 都找不到：不切换，原聊天不动 =====
    _log(f"[SwitchChat] ⚠️ 找不到聊天「{contact_name}」，保持当前聊天")


async def _read_chat_messages(page, limit=5):
    """读取当前聊天的最新消息"""
    await asyncio.sleep(random.uniform(0.5, 1.5))
    try:
        msgs = await page.evaluate(f"""() => {{
            const results = [];
            const all = document.querySelectorAll('[data-pre-plain-text]');
            for (const el of Array.from(all).slice(-{limit * 2})) {{
                const textSpan = el.querySelector('span.selectable-text, span[dir="ltr"]');
                const text = textSpan ? textSpan.innerText.trim() : '';
                if (!text) continue;
                const pre = el.getAttribute('data-pre-plain-text') || '';
                const isIn = el.closest('.message-in') !== null;
                results.push({{
                    role: isIn ? 'received' : 'sent',
                    text: text,
                    time: pre.replace(/[\\[\\]]/g, '').trim()
                }});
            }}
            const received = results.filter(m => m.role === 'received');
            return received.length > 0 ? received.slice(-{limit}) : results.slice(-{limit});
        }}""")
        return msgs if msgs else []
    except:
        return []


def _format_messages(msgs):
    if not msgs:
        return "暂无新消息"
    lines = []
    for m in msgs:
        role = "【客户】" if m["role"] == "received" else "【我】"
        lines.append(f"{role}{m['text']}")
        if m.get("time"):
            lines.append(f"[{m['time']}]")
    return "\n".join(lines)


async def _monitor_loop(page):
    """监控新消息循环（v3: 含心跳 + 定期日志）"""
    consecutive_errors = 0
    not_logged_in_count = 0
    _last_status_log = 0.0
    while _running.is_set():
        try:
            try:
                await page.wait_for_selector(
                    'div[aria-label="Chat list"], div[aria-label="聊天列表"], '
                    'div[aria-label*="chat" i], [data-testid="chat-list"]',
                    timeout=30000)
                not_logged_in_count = 0  # 重置计数
                _update_heartbeat()  # v3: 更新心跳
            except Exception as inner_e:
                err = str(inner_e)
                if "closed" in err.lower() or "target" in err.lower():
                    _log("[Monitor] Chrome窗口已关闭，通知引擎重启...")
                    return  # 退出monitor → cmd_loop退出 → 引擎重启
                not_logged_in_count += 1
                # 前几次不刷日志，避免日志刷屏
                if not_logged_in_count <= 3 or not_logged_in_count % 6 == 0:
                    _log(f"[Monitor] WhatsApp未登录 (已等待{not_logged_in_count * 30}秒)")
                # 只在确实超时后才刷新（每5分钟一次），且刷新后多等一会儿
                if not_logged_in_count >= 10:
                    _log("[Monitor] 5分钟未登录，温和刷新页面...")
                    try:
                        await page.reload(timeout=30000)
                        await asyncio.sleep(10)
                    except Exception as e:
                        err2 = str(e)
                        if "closed" in err2.lower() or "target" in err2.lower():
                            _log("[Monitor] Chrome窗口已关闭，通知引擎重启...")
                            return
                    not_logged_in_count = 0
                await asyncio.sleep(30)
                continue

            consecutive_errors = 0

            # v3: 每 5 分钟输出一次运行状态日志
            now_t = time.time()
            if now_t - _last_status_log > 300:
                hb_ago = _get_heartbeat_ago()
                _last_status_log = now_t
                _log(f"[Monitor] 正常运行中... 心跳={hb_ago:.0f}s前, 已登录=是, 未读检查中")

            unread = await _find_unread_chats(page)
            if unread:
                _log(f"[Monitor] 发现 {len(unread)} 个未读聊天")
                for i, chat_name in enumerate(unread):
                    if not _running.is_set():
                        return
                    _log(f"[Monitor] ({i+1}/{len(unread)}) 处理: {chat_name}")
                    await _switch_chat(page, chat_name)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    msgs = await _read_chat_messages(page, limit=3)
                    if msgs and _on_message_callback:
                        try:
                            _on_message_callback(chat_name, msgs)
                        except Exception as e:
                            _log(f"[Monitor] 回调错误: {e}")
                    # 多个未读时，间隔8-18秒（防风控）
                    if i < len(unread) - 1:
                        await asyncio.sleep(random.uniform(8, 18))
                # 全部处理完后长休息
                await asyncio.sleep(random.uniform(60, 120))
            else:
                await asyncio.sleep(random.uniform(10, 30))

        except Exception as e:
            err = str(e)
            if "closed" in err.lower() or "target" in err.lower():
                _log("[Monitor] Chrome窗口已关闭，通知引擎重启...")
                return
            consecutive_errors += 1
            _log(f"[Monitor] 错误({consecutive_errors}): {e}")
            if consecutive_errors > 10:
                _log("[Monitor] 连续错误，30秒后重试")
                await asyncio.sleep(30)
                consecutive_errors = 0
            else:
                await asyncio.sleep(15)


async def _engine_subprocess_cdp(restart_count=0):
    """v3 稳定版：子进程启动 Chrome → CDP 连接
    优势：
    1. Chrome 是独立进程，不受 Playwright 上下文管理影响
    2. 崩溃后立即检测 (subprocess.poll())，极速恢复
    3. 不走 launch_persistent_context，避免 Windows 下的稳定性问题
    """
    global _page, _browser_context, _chrome_subprocess, _last_heartbeat

    from playwright.async_api import async_playwright

    # 清理旧进程 + 端口
    _stop_chrome_process()
    _kill_chrome_on_port(_CDP_PORT)

    os.makedirs(PROFILE_DIR, exist_ok=True)

    # 启动 Chrome 子进程
    _start_chrome_process()

    _page_ready.clear()
    _page = None

    try:
        # 先获取 DevTools WebSocket URL（直接传 HTTP 地址给 connect_over_cdp 在部分 Playwright 版本有 bug）
        ws_url = _get_devtools_ws_url()
        if not ws_url:
            raise Exception("无法获取 DevTools WebSocket URL")

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(
                ws_url, timeout=30000
            )
            _log(f"[Engine] CDP 连接成功 ({_CDP_PORT})")

            contexts = browser.contexts
            if not contexts:
                raise Exception("CDP: 无浏览器上下文")
            context = contexts[0]
            _browser_context = context

            # 找已有的 WhatsApp Web 标签页，没有就新建
            page = None
            for tab in context.pages:
                if "web.whatsapp.com" in tab.url:
                    page = tab
                    _log("[Engine] 找到已有 WhatsApp 标签页")
                    break

            if not page:
                page = await context.new_page()
                await page.goto("https://web.whatsapp.com",
                                wait_until="domcontentloaded", timeout=60000)

            _page = page
            _page_ready.set()
            _update_heartbeat()
            _log(f"[Engine] WhatsApp Web 已就绪 (Subprocess+CDP PID={_chrome_subprocess.pid})")

            await _engine_cmd_loop(page)
            _log("[Engine] 引擎循环结束")
    except Exception as e:
        raise
    finally:
        # Chrome 崩溃或正常退出 → 停止子进程
        _stop_chrome_process()
        _page = None
        _page_ready.clear()


async def _engine_main_launch():
    """引擎主循环：优先用 subprocess+CDP，失败回退到 launch_persistent_context"""
    global _page, _browser_context, _needs_reauth

    from playwright.async_api import async_playwright

    # 连续崩溃计数器 — 防止无限闪退循环
    global _crash_count
    try:
        _crash_count
    except NameError:
        _crash_count = 0
    _profile_cleaned = False
    _fallback_to_launch = False  # 如果 subprocess 反复失败，回退到 launch_persistent_context
    err = ""

    while _running.is_set():
        err = ""
        _launch_mode = "subprocess_cdp"

        # Profile 损坏保护：连续 3 次崩溃 → 备份 + 标记需要重新扫码
        if _crash_count >= 3 and not _profile_cleaned:
            backup_dir = PROFILE_DIR.rstrip("\\/") + "_corrupted_" + str(int(time.time()))
            _log(f"[Engine] Profile损坏保护，备份→{os.path.basename(backup_dir)}")
            try:
                if os.path.exists(PROFILE_DIR):
                    # 先杀可能占用 profile 的 Chrome 进程
                    _kill_all_chrome_for_profile()
                    time.sleep(1)
                    os.rename(PROFILE_DIR, backup_dir)
                    _needs_reauth = True  # v3: 标记需要重新扫码
                    _log("[Engine] ⚠️ Profile已备份，需要重新扫码登录")
            except Exception as bak_e:
                _log(f"[Engine] 备份profile失败: {bak_e}")
            _profile_cleaned = True
            _crash_count = 0  # 重置计数，用新 profile 重试
            _fallback_to_launch = False  # 新 profile → 重新尝试 subprocess+CDP

        os.makedirs(PROFILE_DIR, exist_ok=True)

        # v3: 优先使用 subprocess+CDP
        try:
            if not _fallback_to_launch:
                _log(f"[Engine] 启动 Chrome (subprocess+CDP, port={_CDP_PORT}, profile={PROFILE_DIR})")
                await _engine_subprocess_cdp(restart_count=_crash_count)
            else:
                raise Exception("已回退到 launch_persistent_context")
        except Exception as e:
            err = str(e)
            _log(f"[Engine] Subprocess+CDP 异常: {err}")
            if not _running.is_set():
                break
            # subprocess 失败 → 尝试 launch_persistent_context 作为回退
            _fallback_to_launch = True

        # 回退：launch_persistent_context
        if _fallback_to_launch and _running.is_set():
            _launch_mode = "persistent_context"
            # 杀干净旧 Chrome 进程，防止 profile 锁冲突
            _log(f"[Engine] 回退前清理 Chrome 进程...")
            _stop_chrome_process()
            _kill_all_chrome_for_profile()
            _kill_chrome_on_port(_CDP_PORT)
            time.sleep(2)

            _log(f"[Engine] 回退→launch_persistent_context (profile={PROFILE_DIR})")
            _page_ready.clear()
            _page = None

            try:
                async with async_playwright() as p:
                    context = await p.chromium.launch_persistent_context(
                        PROFILE_DIR,
                        headless=sys.platform.startswith("linux"),
                        channel="chromium",
                        no_viewport=True,
                        args=[
                            "--start-maximized",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-automation",
                            "--disable-gpu",
                            "--disable-software-rasterizer",
                            "--disable-dev-shm-usage",
                            "--disable-features=VizDisplayCompositor",
                            "--no-sandbox",
                        ],
                        ignore_default_args=["--enable-automation"],
                        handle_sigint=False,
                        handle_sigterm=False,
                        timeout=90000,
                    )
                    _browser_context = context
                    _log("[Engine] Chrome 启动成功 (persistent_context)")
                    _crash_count = 0

                    page = None
                    for tab in context.pages:
                        if "web.whatsapp.com" in tab.url:
                            page = tab
                            break
                    if not page:
                        page = await context.new_page()
                        await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

                    _page = page
                    _page_ready.set()
                    _update_heartbeat()
                    _log("[Engine] WhatsApp Web已就绪 (persistent_context)")

                    await _engine_cmd_loop(page)
                    _log("[Engine] 引擎循环结束")
            except Exception as e2:
                err = str(e2)
                _log(f"[Engine] Persistent_context 也失败: {err}")
                if not _running.is_set():
                    break

        # 重启等待逻辑
        if _running.is_set():
            _crash_count += 1
            is_user_close = "closed" in err.lower() or "target" in err.lower()
            # v3: 大幅缩短等待时间
            if is_user_close:
                wait = 30   # 用户关闭窗口→等30秒（原300秒）
            elif _crash_count >= 5:
                wait = 60   # 5次以上崩溃等60秒
            elif _crash_count >= 3:
                wait = 30   # 3-4次崩溃等30秒
            elif _crash_count >= 2:
                wait = 15   # 第2次崩溃等15秒
            else:
                wait = _CHROME_RESTART_DELAY  # 第1次崩溃等3秒
            reason = "用户关闭" if is_user_close else f"崩溃(第{_crash_count}次)"
            _log(f"[Engine] Chrome已关闭 [{reason}], {_launch_mode}, {wait}秒后重启...")
            await asyncio.sleep(wait)


async def _engine_main_cdp():
    """引擎主循环：通过 CDP 连接到用户已有的 Chrome（127.0.0.1:9222）
    保留此函数用于外部 Chrome 连接场景"""
    global _page, _browser_context

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        _log("[Engine] CDP 连接成功")

        contexts = browser.contexts
        if not contexts:
            raise Exception("CDP: 无浏览器上下文")
        context = contexts[0]
        _browser_context = context

        page = None
        for tab in context.pages:
            url = tab.url
            if "web.whatsapp.com" in url:
                page = tab
                _log("[Engine] 找到已有 WhatsApp 标签页")
                break

        if not page:
            page = await context.new_page()
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

        _page = page
        _page_ready.set()
        _update_heartbeat()
        _log("[Engine] WhatsApp Web已就绪（CDP模式，使用你的Chrome）")

        await _engine_cmd_loop(page)

        _log("[Engine] CDP 模式：保留用户 Chrome")


async def _engine_cmd_loop(page):
    """命令+监控主循环（_engine_main_launch 和 _engine_main_cdp 共用）"""
    monitor_task = asyncio.create_task(_monitor_loop(page))

    try:
        while _running.is_set():
            while not _cmd_queue.empty():
                try:
                    cmd = _cmd_queue.get_nowait()
                    cmd_id = cmd.get("id")
                    result = await _execute_cmd(cmd, page)
                    if cmd_id:
                        _cmd_results[cmd_id] = result
                        if cmd_id in _cmd_events:
                            _cmd_events[cmd_id].set()
                except queue.Empty:
                    break
            await asyncio.sleep(0.5)
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except:
            pass


async def _engine_main():
    """引擎主入口：先试 CDP 连已有 Chrome，失败则启动独立 Chrome"""
    # 快速检查端口 9222（0.5秒超时，不阻塞）
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        result = s.connect_ex(('127.0.0.1', 9222))
        s.close()
        if result == 0:
            await _engine_main_cdp()
            return
    except:
        pass

    _log("[Engine] CDP 不可用（Chrome 调试模式未开启），启动独立 Chrome...")
    await _engine_main_launch()


def _start_engine():
    """在独立线程中启动事件循环"""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_engine_main())
    except Exception as e:
        _log(f"[Engine] 引擎退出: {repr(e)}")
        import traceback
        _log(f"[Engine] 完整异常:\n{traceback.format_exc()}")


def _send_cmd(cmd, timeout=120):
    """发送命令到引擎线程并等待结果"""
    cmd_id = _gen_cmd_id()
    cmd["id"] = cmd_id
    event = threading.Event()
    _cmd_events[cmd_id] = event
    _cmd_queue.put(cmd)
    event.wait(timeout=timeout)
    result = _cmd_results.pop(cmd_id, {"error": "timeout"})
    _cmd_events.pop(cmd_id, None)
    if "error" in result:
        raise Exception(result["error"])
    return result

# ==================== 远程模式（独立服务器） ====================
# 启用后所有函数通过 HTTP 转发到独立 whatsapp_server.py
# 好处：Chrome 永不重启，CRM 重启不影响 WhatsApp 登录状态
_REMOTE_SERVER = None

def _is_remote():
    return _REMOTE_SERVER is not None

def set_remote_server(url):
    """切换到远程模式，后续所有调用转发到独立服务器"""
    global _REMOTE_SERVER
    _REMOTE_SERVER = url

def unset_remote_server():
    """切回本地模式"""
    global _REMOTE_SERVER
    _REMOTE_SERVER = None

def _remote_get(endpoint, timeout=30):
    import urllib.request, json as _json
    url = f"{_REMOTE_SERVER}/{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return _json.loads(r.read().decode())
    except Exception as e:
        raise Exception(f"[WA远程] {e}")

def _remote_post(endpoint, data, timeout=60):
    import urllib.request, json as _json
    url = f"{_REMOTE_SERVER}/{endpoint}"
    body = _json.dumps(data).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _json.loads(r.read().decode())
    except Exception as e:
        raise Exception(f"[WA远程] {e}")


# ==================== 对外接口 (同步) ====================

def _check_engine_alive():
    """检查引擎线程是否活着"""
    global _loop_thread
    if not _loop_thread or not _loop_thread.is_alive():
        _log("[Engine] 引擎线程已死，尝试重启...")
        start_monitor(_on_message_callback)
        # 给新引擎一点时间初始化
        _page_ready.wait(timeout=45)
    if not _loop_thread or not _loop_thread.is_alive():
        raise Exception("WhatsApp引擎未运行，请检查服务器日志")


def send_text(text, contact_name=None):
    """发送文字消息"""
    if _is_remote():
        return _remote_post("send", {"text": text, "contact_name": contact_name or ""})
    _check_engine_alive()
    ok, msg = rate_limiter.can_send()
    if not ok:
        raise Exception(msg)
    _page_ready.wait(timeout=30)
    return _send_cmd({
        "type": "send_text",
        "text": text,
        "contact_name": contact_name,
    })


def send_image_clipboard(image_path, contact_name=None):
    """发送图片"""
    if _is_remote():
        return _remote_post("send-image", {"path": image_path, "contact_name": contact_name or ""})
    _check_engine_alive()
    ok, msg = rate_limiter.can_send()
    if not ok:
        raise Exception(msg)
    _page_ready.wait(timeout=30)
    return _send_cmd({
        "type": "send_file",
        "file_path": image_path,
        "contact_name": contact_name,
        "is_image": True,
    })


def send_media_file(file_path, contact_name=None):
    """发送文件"""
    if _is_remote():
        return _remote_post("send-file", {"path": file_path, "contact_name": contact_name or ""})
    _check_engine_alive()
    ok, msg = rate_limiter.can_send()
    if not ok:
        raise Exception(msg)
    ext = os.path.splitext(file_path)[1].lower()
    is_image = ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    _page_ready.wait(timeout=30)
    return _send_cmd({
        "type": "send_file",
        "file_path": file_path,
        "contact_name": contact_name,
        "is_image": is_image,
    })


def read_messages():
    """读取当前聊天的最新客户消息"""
    if _is_remote():
        return _remote_get("read").get("text", "读取失败")
    _page_ready.wait(timeout=30)
    result = _send_cmd({"type": "read_messages"})
    return result.get("text", "读取失败")


def get_unread_chats():
    """获取所有未读聊天的联系人名"""
    if _is_remote():
        return _remote_get("unread").get("unread", [])
    _page_ready.wait(timeout=30)
    result = _send_cmd({"type": "get_unread"})
    return result.get("unread", [])


def is_logged_in():
    """检查是否已登录（v3: 含心跳验证）"""
    if _is_remote():
        try:
            return _remote_get("logged-in", timeout=10).get("logged_in", False)
        except:
            return False
    try:
        _page_ready.wait(timeout=30)
        result = _send_cmd({"type": "check_logged_in"}, timeout=15)
        logged = result.get("logged_in", False)
        # v3: 心跳保护 — 距离上次成功交互超过 120 秒 → 视为未登录
        hb_ago = _get_heartbeat_ago()
        if logged and hb_ago > 120:
            _log(f"[Engine] 心跳过期 ({hb_ago:.0f}s)，但 DOM 显示已登录，刷新确认...")
            # 尝试温和刷新
            try:
                _send_cmd({"type": "refresh_page"}, timeout=30)
                _log("[Engine] 已发送刷新指令")
            except:
                pass
        return logged
    except:
        return False


def get_monitor_status():
    """获取引擎状态（v3: 含心跳 + 子进程信息）"""
    if _is_remote():
        try:
            return _remote_get("status", timeout=10)
        except:
            return {"running": False, "logged_in": False}
    try:
        _page_ready.wait(timeout=5)
        result = _send_cmd({"type": "get_status"}, timeout=10)
        running = _running.is_set()
        hb_ago = _get_heartbeat_ago()
        subprocess_alive = (_chrome_subprocess is not None
                           and _chrome_subprocess.poll() is None)
        return {
            "running": running,
            "logged_in": result.get("logged_in", False),
            "alive": result.get("alive", False),
            "heartbeat_ago_s": round(hb_ago, 1) if hb_ago >= 0 else -1,
            "subprocess_alive": subprocess_alive,
            "needs_reauth": _needs_reauth,
            "chrome_pid": _chrome_subprocess.pid if _chrome_subprocess else None,
        }
    except:
        return {
            "running": _running.is_set(),
            "logged_in": False,
            "alive": False,
            "heartbeat_ago_s": _get_heartbeat_ago(),
            "subprocess_alive": False,
            "needs_reauth": _needs_reauth,
        }


def refresh_whatsapp_page():
    """手动刷新 WhatsApp Web 页面（二维码过期时用）"""
    if _is_remote():
        try:
            return _remote_post("refresh", {}).get("ok", False)
        except:
            return False
    try:
        _page_ready.wait(timeout=30)
        _send_cmd({"type": "refresh_page"}, timeout=30)
        _log("[引擎] 手动刷新WhatsApp页面")
        return True
    except Exception as e:
        _log(f"[引擎] 刷新失败: {e}")
        return False


def start_monitor(callback=None):
    """启动引擎和自动监控（带看门狗自动重启）"""
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎启动")
        return
    global _on_message_callback, _loop_thread, _running
    if _loop_thread and _loop_thread.is_alive():
        _log("[Engine] 已在运行")
        return

    _on_message_callback = callback
    _running.set()
    _loop_thread = threading.Thread(target=_start_engine, daemon=True)
    _loop_thread.start()
    _log("[Engine] 引擎启动中...")

    # 看门狗：引擎崩了自动重启
    def _watchdog():
        global _page_ready, _loop_thread
        while _running.is_set():
            time.sleep(30)
            if not _loop_thread or not _loop_thread.is_alive():
                _log("[Watchdog] 引擎线程已死，正在重启...")
                _page_ready = threading.Event()
                new_thread = threading.Thread(target=_start_engine, daemon=True)
                new_thread.start()
                _loop_thread = new_thread
                _log("[Watchdog] 引擎已重启")
    threading.Thread(target=_watchdog, daemon=True).start()


def stop_monitor():
    """停止引擎"""
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎停止")
        return
    global _running
    _running.clear()
    _log("[Engine] 引擎停止信号已发送")


def close():
    """完全关闭（v3: 含 Chrome 子进程清理）"""
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎关闭")
        return
    stop_monitor()
    _stop_chrome_process()
    _kill_chrome_on_port(_CDP_PORT)
    _log("[Engine] Chrome 子进程已停止")


def get_health():
    """获取详细健康状态（用于监控和告警）"""
    status = get_monitor_status()
    hb_ago = _get_heartbeat_ago()
    health = {
        "ok": status.get("running") and status.get("subprocess_alive"),
        "running": status.get("running", False),
        "logged_in": status.get("logged_in", False),
        "subprocess_alive": status.get("subprocess_alive", False),
        "heartbeat_ago_s": hb_ago if hb_ago >= 0 else -1,
        "needs_reauth": _needs_reauth,
        "warnings": [],
    }
    # 生成告警
    if not status.get("running"):
        health["warnings"].append("ENGINE_NOT_RUNNING")
    if not status.get("subprocess_alive"):
        health["warnings"].append("CHROME_PROCESS_DEAD")
    if hb_ago > 120:
        health["warnings"].append("HEARTBEAT_STALE")
    if status.get("logged_in") and hb_ago > 300:
        health["warnings"].append("HEARTBEAT_CRITICAL")
    if _needs_reauth:
        health["warnings"].append("NEEDS_REAUTH")
    health["warning_count"] = len(health["warnings"])
    health["healthy"] = len(health["warnings"]) == 0
    return health


# ==================== 兼容旧接口 ====================
def human_click(pos, delay=1):
    pass

def paste_text(text):
    pass

def find_input_box():
    return (0, 0)


# ========= QR Code screenshot for cloud login =========
import base64


async def _capture_qr():
    """截取 WhatsApp 页面中的二维码区域（全屏截图，由调用方保证 page 就绪）"""
    if _page is None:
        return None
    try:
        # 确保有合理的视口大小，让 QR 码居中显示
        await _page.set_viewport_size({"width": 700, "height": 900})

        # 等一小会让 QR 渲染
        await asyncio.sleep(3)

        # 先尝试用 JS 精确定位 QR 码 canvas
        info = await _page.evaluate("""
            () => {
                const canvases = document.querySelectorAll('canvas');
                for (const c of canvases) {
                    if (c.width > 100 && c.height > 100) {
                        const r = c.getBoundingClientRect();
                        if (r.width > 100 && r.height > 100) {
                            return {x: r.x, y: r.y, w: r.width, h: r.height};
                        }
                    }
                }
                return null;
            }
        """)

        if info and info["w"] > 50:
            pad = 20
            clip = {
                "x": max(0, info["x"] - pad),
                "y": max(0, info["y"] - pad),
                "width": info["w"] + pad * 2,
                "height": info["h"] + pad * 2,
            }
            shot = await _page.screenshot(clip=clip, type='png')
            _log(f"[QR] 截取二维码区域 ({info['w']}x{info['h']})")
            return base64.b64encode(shot).decode()

        # 没找到 QR canvas → 全屏截图（headless 下 QR 一般在中央）
        shot = await _page.screenshot(type='png', full_page=False)
        _log(f"[QR] 未找到canvas，全屏截图 ({len(shot)} bytes)")
        return base64.b64encode(shot).decode()
    except Exception as e:
        _log(f"[QR] Capture error: {e}")
        return None


def get_qr_base64():
    """同步获取 QR 码截图（Flask 调用）"""
    if _is_remote():
        try:
            return _remote_get("qr", timeout=15).get("qr")
        except:
            return None
    if not _running.is_set():
        return None
    # 等待页面就绪（最多 45 秒，覆盖引擎首次启动 + 重启）
    if not _page_ready.wait(timeout=45):
        _log("[QR] 等待 page_ready 超时")
        return None
    if _page is None:
        _log("[QR] page_ready 已触发但 _page 仍为 None")
        return None
    import asyncio
    try:
        loop = _loop
        if loop is None or not loop.is_running():
            _log("[QR] 事件循环不可用")
            return None
        future = asyncio.run_coroutine_threadsafe(_capture_qr(), loop)
        return future.result(timeout=15)
    except Exception as e:
        print(f"[QR] get_qr_base64 error: {e}")
        return None
