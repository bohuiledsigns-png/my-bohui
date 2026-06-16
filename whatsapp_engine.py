"""GLOWFORGE WhatsApp Engine — Playwright异步版
直接操作WhatsApp Web DOM，7×24小时自动运行
专用事件循环线程，无多线程冲突
使用 Persistent Context 保持登录状态
"""
import os
import re
import uuid
import time
import random
import queue
import json
import threading
import asyncio

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


def _gen_cmd_id():
    global _cmd_counter
    with _cmd_lock:
        _cmd_counter += 1
        return f"cmd_{_cmd_counter}_{uuid.uuid4().hex[:4]}"


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
    """监控新消息循环（未登录时自动刷新页面）"""
    consecutive_errors = 0
    not_logged_in_count = 0
    while _running.is_set():
        try:
            try:
                await page.wait_for_selector(
                    'div[aria-label="Chat list"], div[aria-label="聊天列表"], '
                    'div[aria-label*="chat" i], [data-testid="chat-list"]',
                    timeout=15000)
                not_logged_in_count = 0  # 重置计数
            except Exception as inner_e:
                err = str(inner_e)
                if "closed" in err.lower() or "target" in err.lower():
                    _log("[Monitor] Chrome窗口已关闭，通知引擎重启...")
                    return  # 退出monitor → cmd_loop退出 → 引擎重启
                not_logged_in_count += 1
                _log(f"[Monitor] WhatsApp未登录 ({not_logged_in_count}/3)")
                # 连续3次未检测到登录 → 刷新页面（二维码过期了）
                if not_logged_in_count >= 3:
                    _log("[Monitor] 二维码可能已过期，自动刷新页面...")
                    try:
                        await page.reload(timeout=60000)
                        await asyncio.sleep(5)
                    except Exception as e:
                        err2 = str(e)
                        if "closed" in err2.lower() or "target" in err2.lower():
                            _log("[Monitor] Chrome窗口已关闭，通知引擎重启...")
                            return
                        _log(f"[Monitor] 刷新页面失败: {e}")
                    not_logged_in_count = 0
                await asyncio.sleep(10)
                continue

            consecutive_errors = 0
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
                _log("[Monitor] 连续错误，5分钟后重试")
                await asyncio.sleep(300)
                consecutive_errors = 0
            else:
                await asyncio.sleep(15)


async def _engine_main_launch():
    """引擎主循环：用 Playwright launch_persistent_context 启动 Chrome
    Playwright 自带进程管理 + profile 持久化，不需要手动轮询端口
    如果用户关闭 Chrome 窗口会自动重启"""
    global _page, _browser_context

    from playwright.async_api import async_playwright

    while _running.is_set():
        # 清掉上次残留的配置（如果有）
        try:
            import shutil
            if os.path.exists(PROFILE_DIR):
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        except:
            pass
        os.makedirs(PROFILE_DIR, exist_ok=True)
        _log(f"[Engine] 启动 Chrome (launch_persistent_context, profile={PROFILE_DIR})")

        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    PROFILE_DIR,
                    headless=False,
                    channel="chrome",
                    no_viewport=True,
                    args=[
                        "--start-maximized",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-automation",
                    ],
                    ignore_default_args=["--enable-automation"],
                    handle_sigint=False,
                    handle_sigterm=False,
                    timeout=60000,
                )
                _browser_context = context
                _log(f"[Engine] Chrome 启动成功")

                # 找已有的 WhatsApp 标签页，没有就新建
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
                _log("[Engine] WhatsApp Web已就绪")

                await _engine_cmd_loop(page)
                _log("[Engine] 引擎循环结束")

                # 不关闭 Chrome（如果还在运行）
                _log("[Engine] 保留 Chrome 进程")
        except Exception as e:
            err = str(e)
            _log(f"[Engine] Chrome异常: {err}")
            if not _running.is_set():
                break

        # 等待一下再重启，防止过快循环
        if _running.is_set():
            _log("[Engine] Chrome已关闭，5秒后重启...")
            await asyncio.sleep(5)


async def _engine_main_cdp():
    """引擎主循环：通过 CDP 连接到用户已有的 Chrome（127.0.0.1:9222）"""
    global _page, _browser_context

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        _log("[Engine] CDP 连接成功")

        # 获取默认浏览器上下文
        contexts = browser.contexts
        if not contexts:
            raise Exception("CDP: 无浏览器上下文")
        context = contexts[0]
        _browser_context = context

        # 找已有的 WhatsApp Web 标签页，没有就新建
        page = None
        for tab in context.pages:
            url = tab.url
            if "web.whatsapp.com" in url:
                page = tab
                _log(f"[Engine] 找到已有 WhatsApp 标签页")
                break

        if not page:
            page = await context.new_page()
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

        _page = page
        _page_ready.set()
        _log("[Engine] WhatsApp Web已就绪（CDP模式，使用你的Chrome）")

        await _engine_cmd_loop(page)

        # CDP 模式不关闭用户 Chrome
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
    """检查是否已登录"""
    if _is_remote():
        try:
            return _remote_get("logged-in", timeout=10).get("logged_in", False)
        except:
            return False
    try:
        _page_ready.wait(timeout=30)
        result = _send_cmd({"type": "check_logged_in"}, timeout=15)
        return result.get("logged_in", False)
    except:
        return False


def get_monitor_status():
    """获取引擎状态"""
    if _is_remote():
        try:
            return _remote_get("status", timeout=10)
        except:
            return {"running": False, "logged_in": False}
    try:
        _page_ready.wait(timeout=5)
        result = _send_cmd({"type": "get_status"}, timeout=10)
        running = _running.is_set()
        return {"running": running, "logged_in": result.get("logged_in", False)}
    except:
        return {"running": _running.is_set(), "logged_in": False}


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
    """完全关闭"""
    if _is_remote():
        _log("[Engine] 远程模式，忽略本地引擎关闭")
        return
    stop_monitor()


# ==================== 兼容旧接口 ====================
def human_click(pos, delay=1):
    pass

def paste_text(text):
    pass

def find_input_box():
    return (0, 0)
