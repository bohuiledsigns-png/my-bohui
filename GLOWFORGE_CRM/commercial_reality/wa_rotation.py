"""WAAccountManager — WhatsApp 多号轮换管理器

每个号 = 独立 Chrome 进程 + 独立 Profile + 独立限速。
通过 monkey-patch whatsapp_engine.send_text 让所有调用者无感切换。

架构:
  WAAccountManager (单例)
    ├── AccountEngine #1 (主号, :9223, 活跃)
    ├── AccountEngine #2 (备用, :9224, standby)
    └── AccountEngine #3 (备用, :9225, standby)
    健康检查线程 (60s) → 自动 failover
"""
import json
import logging
import os
import sqlite3
import subprocess
import threading
import time

logger = logging.getLogger("glowforge.commercial_reality.wa_rotation")

# ── 默认账号配置 ──
_DEFAULT_ACCOUNTS = [
    {"name": "主号", "profile_dir": "account_1", "cdp_port": 9223, "priority": 0},
    {"name": "备用1", "profile_dir": "account_2", "cdp_port": 9224, "priority": 1},
    {"name": "备用2", "profile_dir": "account_3", "cdp_port": 9225, "priority": 2},
]

# 默认 Chrome 路径（查找可能的安装位置）
_CHROME_PATHS = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe"),
]


def _find_chrome():
    for p in _CHROME_PATHS:
        if os.path.isfile(p):
            return p
    # 尝试从 PATH 找
    try:
        import shutil
        return shutil.which("chrome") or shutil.which("google-chrome") or "chrome"
    except Exception:
        return "chrome"


# ─────────────────────────────────────────────
# AccountEngine — 单个 WhatsApp 号的管理
# ─────────────────────────────────────────────

class AccountEngine:
    """管理一个 WhatsApp 账号的 Chrome 进程 + Playwright 页面"""

    def __init__(self, account_id: int, name: str, profile_dir: str, cdp_port: int, accounts_base: str):
        self.id = account_id
        self.name = name
        self.profile_path = os.path.join(accounts_base, profile_dir)
        self.cdp_port = cdp_port
        self._chrome_proc = None
        self._browser = None
        self._page = None
        self._playwright = None
        self._alive = False
        self._logged_in = False
        self._last_heartbeat = 0.0
        self._lock = threading.Lock()
        # 每个号独立限速
        self._rate_timestamps = []
        self._rate_max_per_hour = 15
        self._rate_min_interval = 30

    def _rate_can_send(self) -> tuple:
        """检查本账号的发送限速"""
        now = time.time()
        with self._lock:
            self._rate_timestamps = [t for t in self._rate_timestamps if now - t < 3600]
            if len(self._rate_timestamps) >= self._rate_max_per_hour:
                return False, "已达每小时%d条上限" % self._rate_max_per_hour
            if self._rate_timestamps and now - self._rate_timestamps[-1] < self._rate_min_interval:
                wait = int(self._rate_min_interval - (now - self._rate_timestamps[-1]))
                return False, "请等待%d秒" % wait
            return True, "ok"

    def launch(self) -> bool:
        """启动 Chrome 子进程 + 连接 Playwright"""
        try:
            chrome_path = _find_chrome()
            os.makedirs(self.profile_path, exist_ok=True)

            # 启动 Chrome
            args = [
                chrome_path,
                f"--remote-debugging-port={self.cdp_port}",
                f"--user-data-dir={self.profile_path}",
                "--no-first-run", "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
                "--disable-features=ChromeWhatsNewUI",
                "--window-size=1280,720",
                "--window-position=0,0",
            ]
            # keep proxy env for internet (needed for WhatsApp in China),
            # but add NO_PROXY so DevTools/localhost bypass the proxy
            _chrome_env = os.environ.copy()
            _chrome_env.setdefault("NO_PROXY", "localhost,127.0.0.1")
            self._chrome_proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_chrome_env,
            )
            logger.info("[Account#%d %s] Chrome launched on port %d", self.id, self.name, self.cdp_port)

            # 等待 DevTools 就绪
            self._wait_devtools()

            # 连接 Playwright
            import asyncio
            from playwright.async_api import async_playwright

            async def _connect():
                self._playwright = await async_playwright().start()
                ws_url = await self._get_devtools_ws_url_async()
                if not ws_url:
                    return False
                self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)
                # 获取或创建页面
                pages = self._browser.contexts[0].pages if self._browser.contexts else []
                if pages:
                    self._page = pages[0]
                else:
                    self._page = await self._browser.new_page()
                # 导航到 WhatsApp Web
                await self._page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
                await asyncio.sleep(3)
                self._alive = True
                self._last_heartbeat = time.time()
                return True

            ok = asyncio.run(_connect())
            if ok:
                logger.info("[Account#%d %s] Playwright connected", self.id, self.name)
            else:
                logger.warning("[Account#%d %s] Playwright connect failed", self.id, self.name)
            return ok

        except Exception as e:
            logger.error("[Account#%d %s] Launch failed: %s", self.id, self.name, e)
            self._alive = False
            return False

    def _wait_devtools(self, timeout=15):
        """等待 Chrome DevTools HTTP endpoint 就绪"""
        import urllib.request
        # bypass proxy for localhost DevTools
        _no_proxy_handler = urllib.request.ProxyHandler({})
        _opener = urllib.request.build_opener(_no_proxy_handler)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = _opener.open(
                    "http://127.0.0.1:%d/json/version" % self.cdp_port, timeout=2
                )
                if resp.status == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError("[Account#%d] DevTools not ready after %ds" % (self.id, timeout))

    async def _get_devtools_ws_url_async(self):
        """Playwright 异步获取 DevTools WebSocket URL"""
        import urllib.request
        import json as _json
        _no_proxy_handler = urllib.request.ProxyHandler({})
        _opener = urllib.request.build_opener(_no_proxy_handler)
        try:
            resp = _opener.open(
                "http://127.0.0.1:%d/json/version" % self.cdp_port, timeout=5
            )
            data = _json.loads(resp.read().decode())
            return data.get("webSocketDebuggerUrl", "")
        except Exception:
            return ""

    def send_text(self, text: str, contact_name: str = "") -> dict:
        """通过本账号发送 WhatsApp 消息

        Returns:
            {"ok": True} 或 {"ok": False, "error": str}
        """
        if not self._alive or not self._page:
            return {"ok": False, "error": "引擎未运行"}

        # 限速检查
        rate_ok, rate_msg = self._rate_can_send()
        if not rate_ok:
            return {"ok": False, "error": rate_msg}

        try:
            import asyncio

            async def _do_send():
                page = self._page

                # 心跳
                try:
                    await page.evaluate("1")
                    self._last_heartbeat = time.time()
                except Exception:
                    self._alive = False
                    return {"ok": False, "error": "页面已断开"}

                # 如果指定了联系人，切换聊天
                if contact_name:
                    # 搜索联系人
                    try:
                        search_box = page.locator("div[contenteditable='true']").first
                        await search_box.click()
                        await asyncio.sleep(0.5)
                        await search_box.fill(contact_name)
                        await asyncio.sleep(1)
                        # 点击搜索结果
                        result = page.locator(f"span[title='{contact_name}']").first
                        if await result.is_visible():
                            await result.click()
                            await asyncio.sleep(1)
                        else:
                            # 尝试更宽松的匹配
                            chat_items = page.locator("div[role='row']").first
                            if await chat_items.is_visible():
                                await chat_items.click()
                                await asyncio.sleep(1)
                    except Exception as e:
                        logger.warning("[Account#%d] Switch chat '%s' failed: %s", self.id, contact_name, e)

                # 输入消息
                try:
                    msg_box = page.locator("div[aria-placeholder='Type a message']").first
                    if not await msg_box.is_visible():
                        msg_box = page.locator("div[contenteditable='true']").last
                    await msg_box.click()
                    await asyncio.sleep(0.3)
                    await msg_box.fill(text)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1.5)
                except Exception as e:
                    return {"ok": False, "error": "发送失败: %s" % e}

                # 记录限速
                with self._lock:
                    self._rate_timestamps.append(time.time())

                return {"ok": True}

            return asyncio.run(_do_send())

        except Exception as e:
            logger.error("[Account#%d] send_text failed: %s", self.id, e)
            return {"ok": False, "error": str(e)}

    def check_health(self) -> dict:
        """检查账号健康状态"""
        if not self._alive or not self._page or not self._chrome_proc:
            self._alive = False
            return {"alive": False, "logged_in": False, "heartbeat_ago": 999}

        # 检查 Chrome 进程
        proc_alive = self._chrome_proc.poll() is None
        if not proc_alive:
            self._alive = False
            return {"alive": False, "logged_in": False, "heartbeat_ago": 999}

        try:
            import asyncio

            async def _check():
                # 心跳
                try:
                    await self._page.evaluate("1")
                    self._alive = True
                    self._last_heartbeat = time.time()
                except Exception:
                    self._alive = False
                    return {"alive": False, "logged_in": False, "heartbeat_ago": 999}

                # 检查登录状态
                try:
                    has_chat_list = await self._page.evaluate(
                        "() => document.querySelector('div[role=\"row\"]') !== null"
                    )
                    self._logged_in = has_chat_list
                except Exception:
                    self._logged_in = False

                return {
                    "alive": True,
                    "logged_in": self._logged_in,
                    "heartbeat_ago": round(time.time() - self._last_heartbeat, 1),
                }

            return asyncio.run(_check())

        except Exception as e:
            logger.warning("[Account#%d] Health check failed: %s", self.id, e)
            self._alive = False
            return {"alive": False, "logged_in": False, "heartbeat_ago": 999}

    def close(self):
        """关闭本账号的 Chrome + Playwright"""
        import asyncio
        try:
            asyncio.run(self._close_async())
        except Exception:
            pass

    async def _close_async(self):
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        if self._chrome_proc:
            try:
                self._chrome_proc.kill()
            except Exception:
                pass
        self._alive = False
        logger.info("[Account#%d %s] Closed", self.id, self.name)


# ─────────────────────────────────────────────
# WAAccountManager — 全局单例管理器
# ─────────────────────────────────────────────

class WAAccountManager:
    """多号轮换管理器"""

    def __init__(self):
        self._accounts: dict[int, AccountEngine] = {}
        self._db_path = ""
        self._active_id = 0
        self._lock = threading.Lock()
        self._health_thread_running = False
        self._stop_event = threading.Event()
        self._accounts_base = ""

    def init_default_accounts(self, db_path: str):
        """初始化账号表（首次运行时创建默认 3 个账号）"""
        self._db_path = db_path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._accounts_base = os.path.join(base_dir, ".whatsapp_session", "accounts")
        os.makedirs(self._accounts_base, exist_ok=True)

        conn = sqlite3.connect(db_path)
        try:
            existing = conn.execute("SELECT COUNT(*) FROM wa_accounts").fetchone()[0]
            if existing == 0:
                for acct in _DEFAULT_ACCOUNTS:
                    conn.execute(
                        "INSERT INTO wa_accounts (name, profile_dir, cdp_port, priority, status) VALUES (?, ?, ?, ?, 'inactive')",
                        (acct["name"], acct["profile_dir"], acct["cdp_port"], acct["priority"]),
                    )
                    profile_path = os.path.join(self._accounts_base, acct["profile_dir"])
                    os.makedirs(profile_path, exist_ok=True)
                    logger.info("[WARotation] Created account: %s (%s)", acct["name"], profile_path)
                conn.commit()
                logger.info("[WARotation] Default 3 accounts created")
            conn.close()
        except Exception as e:
            logger.error("[WARotation] Init accounts failed: %s", e)

    def _load_accounts_from_db(self) -> list[dict]:
        """从 DB 读取账号配置"""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM wa_accounts ORDER BY priority ASC"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("[WARotation] Load accounts failed: %s", e)
            return []

    def _update_account_status(self, account_id: int, status: str):
        """更新 DB 中的账号状态"""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE wa_accounts SET status=?, last_health_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, account_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[WARotation] Update status failed: %s", e)

    def launch_all(self):
        """启动所有非 disabled 的账号"""
        accounts = self._load_accounts_from_db()
        for acct in accounts:
            if acct["status"] == "disabled":
                continue
            engine = AccountEngine(
                account_id=acct["id"],
                name=acct["name"],
                profile_dir=acct["profile_dir"],
                cdp_port=acct["cdp_port"],
                accounts_base=self._accounts_base,
            )
            ok = engine.launch()
            self._accounts[acct["id"]] = engine
            if ok:
                # 首次启动设为 standby（等待扫码）
                if acct["status"] in ("inactive",):
                    self._update_account_status(acct["id"], "standby")
                logger.info("[WARotation] Account #%d %s launched (%s)", acct["id"], acct["name"], "OK" if ok else "FAIL")
            else:
                self._update_account_status(acct["id"], "offline")

        # 如果没有活跃账号，尝试激活第一个可用的
        if self._active_id == 0 or self._active_id not in self._accounts:
            self._try_activate_first()

    def _try_activate_first(self):
        """激活第一个可用的 standby 账号"""
        for aid, engine in self._accounts.items():
            health = engine.check_health()
            if health.get("logged_in"):
                with self._lock:
                    self._active_id = aid
                self._update_account_status(aid, "active")
                logger.info("[WARotation] Activated account #%d %s", aid, engine.name)
                return True
        logger.warning("[WARotation] No logged-in account available")
        return False

    def get_active(self) -> AccountEngine | None:
        """获取当前活跃账号引擎"""
        with self._lock:
            return self._accounts.get(self._active_id)

    def send_text(self, text: str, contact_name: str = "") -> dict:
        """发送消息 — 自动路由到活跃账号，失败时 failover 重试一次"""
        engine = self.get_active()
        if not engine:
            # 尝试激活
            self._try_activate_first()
            engine = self.get_active()
        if not engine:
            return {"ok": False, "error": "无可用账号"}

        result = engine.send_text(text, contact_name)
        if not result.get("ok"):
            # 发送失败 → failover 再试一次
            logger.warning("[WARotation] Send failed on #%d, failing over...", self._active_id)
            self.failover()
            engine2 = self.get_active()
            if engine2:
                logger.info("[WARotation] Retrying on #%d", engine2.id)
                return engine2.send_text(text, contact_name)
        return result

    def failover(self) -> dict:
        """切换到下一个可用账号"""
        with self._lock:
            old_id = self._active_id
            if old_id and old_id in self._accounts:
                self._update_account_status(old_id, "offline")

            # 找优先级最高的 logged_in 账号
            new_id = 0
            for aid, engine in sorted(self._accounts.items()):
                if aid == old_id:
                    continue
                health = engine.check_health()
                if health.get("logged_in"):
                    new_id = aid
                    break

            if new_id:
                self._active_id = new_id
                self._update_account_status(new_id, "active")
                logger.info("[WARotation] Failover: #%d → #%d %s", old_id, new_id, self._accounts[new_id].name)
                return {"ok": True, "from": old_id, "to": new_id}
            else:
                logger.error("[WARotation] Failover failed — no available account!")
                return {"ok": False, "error": "无可用账号"}

    def check_all_health(self) -> list[dict]:
        """检查所有账号健康状态"""
        results = []
        for aid, engine in list(self._accounts.items()):
            health = engine.check_health()
            health["id"] = aid
            health["name"] = engine.name
            results.append(health)
            # 如果活跃号离线了，触发 failover
            if aid == self._active_id and not health.get("logged_in"):
                logger.warning("[WARotation] Active account #%d offline, triggering failover", aid)
                self._update_account_status(aid, "offline")
                self.failover()
        return results

    def get_status(self) -> dict:
        """获取所有账号状态（给管理页面用）"""
        accounts_config = self._load_accounts_from_db()
        accounts = []
        for acct in accounts_config:
            engine = self._accounts.get(acct["id"])
            health = engine.check_health() if engine else {"alive": False, "logged_in": False, "heartbeat_ago": 999}
            accounts.append({
                "id": acct["id"],
                "name": acct["name"],
                "profile_dir": acct["profile_dir"],
                "cdp_port": acct["cdp_port"],
                "status": acct["status"],
                "priority": acct["priority"],
                "last_health_at": acct["last_health_at"],
                "alive": health.get("alive", False),
                "logged_in": health.get("logged_in", False),
                "heartbeat_ago": health.get("heartbeat_ago", 999),
                "is_active": acct["id"] == self._active_id,
            })
        return {
            "accounts": accounts,
            "active_id": self._active_id,
            "total": len(accounts),
        }

    def toggle_account(self, account_id: int) -> dict:
        """启用/禁用某个账号"""
        try:
            conn = sqlite3.connect(self._db_path)
            current = conn.execute(
                "SELECT status FROM wa_accounts WHERE id=?", (account_id,)
            ).fetchone()
            if not current:
                conn.close()
                return {"ok": False, "error": "账号不存在"}

            new_status = "disabled" if current[0] != "disabled" else "standby"
            conn.execute("UPDATE wa_accounts SET status=? WHERE id=?", (new_status, account_id))
            conn.commit()
            conn.close()

            if new_status == "standby" and account_id in self._accounts:
                # 重新启动
                engine = self._accounts[account_id]
                ok = engine.launch()
                if not ok:
                    return {"ok": False, "error": "重启失败"}

            if new_status == "disabled" and account_id in self._accounts:
                self._accounts[account_id].close()
                del self._accounts[account_id]

            logger.info("[WARotation] Account #%d → %s", account_id, new_status)
            return {"ok": True, "status": new_status}
        except Exception as e:
            logger.error("[WARotation] Toggle account failed: %s", e)
            return {"ok": False, "error": str(e)}

    def close_all(self):
        """关闭所有账号"""
        for aid, engine in list(self._accounts.items()):
            engine.close()
        self._accounts.clear()
        self._active_id = 0

    def start_health_monitor(self, interval: int = 60):
        """启动后台健康检查线程"""
        if self._health_thread_running:
            return
        self._health_thread_running = True
        self._stop_event.clear()
        t = threading.Thread(target=self._health_loop, args=(interval,), daemon=True, name="WARotationHealth")
        t.start()
        logger.info("[WARotation] Health monitor started (interval=%ds)", interval)

    def stop_health_monitor(self):
        self._stop_event.set()
        self._health_thread_running = False

    def _health_loop(self, interval: int):
        while not self._stop_event.is_set():
            try:
                self.check_all_health()
            except Exception as e:
                logger.error("[WARotation] Health loop error: %s", e)
            self._stop_event.wait(interval)

    @property
    def all_healthy(self) -> bool:
        """是否至少有一个账号在线"""
        for engine in self._accounts.values():
            h = engine.check_health()
            if h.get("logged_in"):
                return True
        return False

    @property
    def all_offline(self) -> bool:
        return not self.all_healthy


# ── 模块级单例 ──
manager = WAAccountManager()
