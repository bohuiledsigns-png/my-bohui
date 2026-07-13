"""V8 Execution Kernel — IdempotencyGuard + WorkerLoop + ExecutionStateMachine

三层结构:
1. IdempotencyGuard — 防重复执行（execution_key 唯一性）
2. WorkerLoop — 消费循环（lock + retry + DLQ）
3. ExecutionStateMachine — 状态转换验证

使用方式:
    from execution.kernel import ExecutionKernel
    kernel = ExecutionKernel()
    kernel.register_handler("send_message", my_handler_fn)
    kernel.start()  # 启动 worker loop 守护线程
"""

import hashlib
import json
import logging
import threading
import time
import traceback

logger = logging.getLogger("glowforge.execution_kernel")

# ==================== Execution State Machine ====================

class ExecutionStateMachine:
    """执行状态机 — 确保状态转换合法，防止状态错乱"""

    # 合法转换映射: from_state → [to_states]
    VALID_TRANSITIONS = {
        "pending":    ["running", "cancelled", "hold"],  # V8.3: gate can set hold
        "running":    ["completed", "failed"],
        "failed":     ["pending", "dead"],       # retry → pending, max → dead
        "dead":       [],                         # terminal
        "completed":  [],                         # terminal
        "cancelled":  [],                         # terminal
        "blocked":    ["pending", "dead"],        # 人工可放行或弃用
        "hold":       ["pending", "dead"],        # V8.3: release or abandon
    }

    @classmethod
    def can_transition(cls, from_status, to_status):
        """检查状态转换是否合法"""
        allowed = cls.VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    @classmethod
    def assert_transition(cls, from_status, to_status, task_id=None):
        """断言转换合法，非法时抛出 ValueError"""
        if not cls.can_transition(from_status, to_status):
            raise ValueError(
                f"Execution state machine: illegal transition "
                f"{from_status} → {to_status} (task_id={task_id})"
            )

    @classmethod
    def is_terminal(cls, status):
        """检查是否为终态"""
        return status in ("completed", "dead", "cancelled")

    @classmethod
    def is_active(cls, status):
        """检查是否为活跃状态（可被 worker 处理）"""
        return status in ("pending", "running")


# ==================== Idempotency Guard ====================

class IdempotencyGuard:
    """防重复执行

    核心逻辑:
        execution_key = hash(message_id + action_type + order_id)
        UNIQUE 约束保证同一 key 不会重复入队
        已存在且 status ∈ {running, completed, dead} → 跳过

    使用:
        guard = IdempotencyGuard()
        key = guard.build_key(msg_id, "send_quote", order_id=42)
        if guard.should_skip(key):
            return  # 已执行过
    """

    @staticmethod
    def build_key(message_id, action_type, order_id=None, customer_id=None):
        """构建确定性 execution_key

        参数:
            message_id: 消息 ID（WhatsApp message_id 或 UUID）
            action_type: 动作类型（send_quote, create_order, etc.）
            order_id: 订单 ID（可选）
            customer_id: 客户 ID（可选）
        返回:
            str: 32 字符十六进制 hash
        """
        raw = f"{message_id}:{action_type}:{order_id or ''}:{customer_id or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def build_key_from_payload(payload):
        """从执行 payload 中提取字段构建 key"""
        msg_id = payload.get("message_id") or payload.get("source_message_id") or ""
        action = payload.get("action_type") or payload.get("task_type", "")
        oid = payload.get("order_id") or payload.get("order", {}).get("id")
        cid = payload.get("customer_id")
        return IdempotencyGuard.build_key(msg_id, action, oid, cid)

    def __init__(self, db_path=None):
        if db_path is None:
            from execution.execution_queue import DB_PATH
            db_path = DB_PATH
        self._db_path = db_path

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def should_skip(self, execution_key):
        """检查 execution_key 是否应跳过

        返回:
            True = 该 key 已存在且处于活跃/终态，应跳过
            False = 该 key 不存在或已失败，可以执行
        """
        if not execution_key:
            return False
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT status FROM execution_queue WHERE execution_key=? LIMIT 1",
                (execution_key,),
            ).fetchone()
            conn.close()
            if row is None:
                return False
            status = row["status"]
            # running/completed/dead → 跳过
            # failed/pending → 允许（failed 可重试，pending 可能是旧任务）
            return status in ("running", "completed", "dead")
        except Exception as e:
            logger.warning("[Idempotency] check failed (allowing): %s", e)
            return False

    def get_existing(self, execution_key):
        """获取已存在的执行记录（用于检查进度）"""
        if not execution_key:
            return None
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id, status, retry_count, error FROM execution_queue WHERE execution_key=? LIMIT 1",
                (execution_key,),
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def register(self, execution_key, queue_id):
        """将 execution_key 绑定到 queue_id

        在 enqueue 后调用，写入 execution_key 到队列记录。
        """
        if not execution_key or not queue_id:
            return False
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE execution_queue SET execution_key=? WHERE id=?",
                (execution_key, queue_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning("[Idempotency] register failed: %s", e)
            return False


# ==================== DLQ (Dead Letter Queue) ====================

class DeadLetterQueue:
    """死信队列 — 超过重试次数的任务移到这里

    表结构（在 database.py 中创建）:
        execution_dlq (
            id INTEGER PRIMARY KEY,
            original_id INTEGER,
            execution_key TEXT,
            task_type TEXT,
            payload_json TEXT,
            error TEXT,
            retry_count INTEGER,
            moved_at TIMESTAMP
        )
    """

    def __init__(self, db_path=None):
        if db_path is None:
            from execution.execution_queue import DB_PATH
            db_path = DB_PATH
        self._db_path = db_path

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def move_to_dlq(self, queue_id, task_type, execution_key, payload, error, retry_count):
        """将失败任务移入死信队列"""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO execution_dlq
                   (original_id, execution_key, task_type, payload_json, error, retry_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (queue_id, execution_key or "", task_type,
                 json.dumps(payload, ensure_ascii=False) if payload else "{}",
                 str(error)[:1000], retry_count),
            )
            conn.commit()
            conn.close()
            logger.info("[DLQ] Task %d (%s) moved to dead letter queue", queue_id, task_type)
            return True
        except Exception as e:
            logger.error("[DLQ] Failed to move task %d: %s", queue_id, e)
            return False

    def list_dlq(self, limit=50):
        """列出死信队列"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM execution_dlq ORDER BY moved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[DLQ] list failed: %s", e)
            return []

    def requeue_from_dlq(self, dlq_id):
        """将死信任务重新放回执行队列"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM execution_dlq WHERE id=?", (dlq_id,)
            ).fetchone()
            if not row:
                conn.close()
                return None
            d = dict(row)

            # 重新入队
            from execution.execution_queue import ExecutionQueue
            q = ExecutionQueue(self._db_path)
            new_id = q.enqueue(
                task_type=d["task_type"],
                payload=json.loads(d["payload_json"] or "{}"),
                source_agent="dlq_requeue",
            )

            # 删除 DLQ 记录
            conn.execute("DELETE FROM execution_dlq WHERE id=?", (dlq_id,))
            conn.commit()
            conn.close()
            logger.info("[DLQ] Requeued task %d (was %s) → queue id %d",
                        dlq_id, d["task_type"], new_id)
            return new_id
        except Exception as e:
            logger.error("[DLQ] requeue failed: %s", e)
            return None


# ==================== Worker Loop ====================

class WorkerLoop:
    """执行消费循环 — 单线程，带 lock + retry + DLQ

    职责:
        1. 轮询 pending 任务
        2. 按 task_type 分派到注册的 handler
        3. 成功 → mark completed
        4. 失败 → retry 或 move to DLQ
        5. 清理 stale locks
    """

    def __init__(self, queue, interval=5, max_retries=3, stale_lock_timeout=300):
        """
        参数:
            queue: ExecutionQueue 实例
            interval: 轮询间隔（秒）
            max_retries: 最大重试次数
            stale_lock_timeout: 锁超时（秒）
        """
        self._queue = queue
        self._interval = interval
        self._max_retries = max_retries
        self._stale_lock_timeout = stale_lock_timeout
        self._handlers = {}       # task_type → callable
        self._running = False
        self._thread = None
        self._stats = {
            "total_processed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_dlq": 0,
            "started_at": None,
        }
        self._guard = IdempotencyGuard()
        self._dlq = DeadLetterQueue()
        self._business_gate = None  # V8.3: cached lazy instance
        self._ccm = None            # V8.5-B: cached lazy ConstraintCausalMemory

        # V8.2c: side-effect isolation — per-key mutex
        self._processing_locks = {}       # execution_key → threading.Lock
        self._processing_locks_lock = threading.Lock()

    def register_handler(self, task_type, handler_fn):
        """注册任务处理器

        handler_fn(task_dict) → dict 或 None
            - 返回 dict 作为 result_json
            - 抛出异常 → 触发重试
        """
        self._handlers[task_type] = handler_fn
        logger.info("[WorkerLoop] Registered handler: %s", task_type)

    def register_handlers(self, handler_map):
        """批量注册处理器"""
        for task_type, handler_fn in handler_map.items():
            self.register_handler(task_type, handler_fn)

    @property
    def is_running(self):
        return self._running

    def start(self):
        """启动 worker loop 守护线程"""
        if self._running:
            logger.warning("[WorkerLoop] Already running")
            return

        self._running = True
        self._stats["started_at"] = time.time()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="V8WorkerLoop")
        self._thread.start()
        logger.info("[WorkerLoop] Started (interval=%ds, max_retries=%d)",
                    self._interval, self._max_retries)

    def stop(self):
        """停止 worker loop"""
        self._running = False
        logger.info("[WorkerLoop] Stop signal sent")

    def get_stats(self):
        """返回运行统计"""
        stats = dict(self._stats)
        if stats["started_at"]:
            stats["uptime_seconds"] = int(time.time() - stats["started_at"])
        stats["handler_count"] = len(self._handlers)
        stats["is_running"] = self._running
        return stats

    # ── Internal ──

    def _run_loop(self):
        """主循环"""
        cleanup_cycle = 0
        while self._running:
            try:
                # 每 10 轮清理一次 stale locks
                cleanup_cycle += 1
                if cleanup_cycle >= 10:
                    self._queue.cleanup_stale_locks(self._stale_lock_timeout)
                    cleanup_cycle = 0

                # 出队
                tasks = self._queue.dequeue("v8_kernel", batch_size=5)
                for task in tasks:
                    self._process_task(task)

            except Exception as e:
                logger.error("[WorkerLoop] Cycle error: %s", e)

            time.sleep(self._interval)

        logger.info("[WorkerLoop] Stopped")

    def _process_task(self, task):
        """处理单个任务 — V8.3: V7 recheck + Business Policy Gate + side-effect isolation"""
        tid = task["id"]
        task_type = task["task_type"]
        execution_key = task.get("execution_key", "")
        self._stats["total_processed"] += 1

        # 1. Idempotency check（运行时二次确认）
        if execution_key:
            existing = self._guard.get_existing(execution_key)
            if existing and existing["status"] in ("completed", "dead"):
                logger.info("[WorkerLoop] Idempotency skip task %d (%s): already %s",
                            tid, task_type, existing["status"])
                self._queue.complete(tid, {"skipped": True, "reason": "idempotency"})
                return

        # 2. 找处理器
        handler = self._handlers.get(task_type)
        if handler is None:
            logger.warning("[WorkerLoop] No handler for task_type=%s (task %d), marking failed",
                          task_type, tid)
            self._queue.fail(tid, f"No handler registered for {task_type}")
            self._stats["total_failed"] += 1
            return

        # 3. V8.3: V7 Firewall recheck（执行前二次确认）
        try:
            v7 = self._queue.recheck_firewall(tid)
            if v7 == "BLOCK":
                logger.info("[WorkerLoop] V7 recheck BLOCKED task %d (%s)", tid, task_type)
                self._stats["total_failed"] += 1
                return
        except Exception as e:
            logger.warning("[WorkerLoop] V7 recheck failed (allowing): %s", e)

        # 4. V8.3: Business Policy Gate（硬门控）
        # Parse payload once — reused by both gate and handler
        payload = json.loads(task.get("payload_json", "{}"))

        # HOLD-retry-loop prevention: skip gate if task was previously held and human-released
        _skip_gate = False
        if task.get("status") == "pending":
            try:
                _tl = json.loads(task.get("trace_log", "[]"))
                if any(e.get("event") == "released_from_hold" for e in _tl):
                    logger.debug("[WorkerLoop] Skip gate for task %d: was released from hold", tid)
                    _skip_gate = True
            except Exception:
                pass

        gate = self._get_business_gate() if not _skip_gate else None
        _snapshot_id = None
        if gate is not None:
            try:
                customer_id = payload.get("customer_id")
                result = gate.evaluate(task_type, payload, customer_id, task_id=tid)
                _snapshot_id = getattr(result, "snapshot_id", None)
                if result.is_blocked():
                    reason = f"[V8.3 BLOCK] {result.reason}"
                    logger.info("[WorkerLoop] Gate BLOCKED task %d (%s): %s",
                                tid, task_type, result.reason)
                    self._queue.fail(tid, reason)
                    self._stats["total_failed"] += 1
                    # V8.5-B: bind pre_execution → blocked
                    self._ccm_bind(_snapshot_id, tid, "pre_execution", "blocked")
                    return
                if result.is_hold():
                    logger.info("[WorkerLoop] Gate HELD task %d (%s): %s",
                                tid, task_type, result.reason)
                    self._queue.set_hold(tid, result.reason)
                    self._enqueue_hold_for_review(result, task)
                    # V8.5-B: bind pre_execution → held
                    self._ccm_bind(_snapshot_id, tid, "pre_execution", "held")
                    return
                # ALLOW: bind pre_execution → allowed (before handler)
                self._ccm_bind(_snapshot_id, tid, "pre_execution", "allowed")
            except Exception as e:
                logger.warning("[WorkerLoop] Gate evaluation failed (allowing): %s", e)

        # 5. V8.2c: side-effect isolation — per-key mutex
        key_lock = self._acquire_key_lock(execution_key)
        if key_lock is False:
            logger.info("[WorkerLoop] Side-effect skip task %d (%s): key %s in-flight",
                        tid, task_type, execution_key[:12] if execution_key else "?")
            self._queue.requeue(tid, delay_seconds=10)
            return

        # 6. 执行（复用步骤4已解析的 payload）
        try:
            result = handler(payload)
            self._queue.complete(tid, result or {})
            self._stats["total_success"] += 1
            logger.debug("[WorkerLoop] Task %d (%s) completed", tid, task_type)
            # V8.5-B: bind post_execution → completed
            self._ccm_bind(_snapshot_id, tid, "post_execution", "completed")

        except Exception as e:
            error_str = f"{type(e).__name__}: {e}"[:500]
            logger.warning("[WorkerLoop] Task %d (%s) failed: %s", tid, task_type, error_str)
            # V8.5-B: bind post_execution → failed
            self._ccm_bind(_snapshot_id, tid, "post_execution", "failed")

            # V8.2a: fail() is pure state setter — DB sets status='failed', never re-pends
            self._queue.fail(tid, error_str)

            retry_count = (task.get("retry_count", 0) or 0) + 1
            if retry_count >= self._max_retries:
                # 超过最大重试 → 移入 DLQ
                self._dlq.move_to_dlq(
                    tid, task_type, execution_key,
                    json.loads(task.get("payload_json", "{}")),
                    error_str, retry_count,
                )
                self._stats["total_dlq"] += 1
                logger.error("[WorkerLoop] Task %d (%s) → DLQ after %d retries",
                             tid, task_type, retry_count)
            else:
                # WorkerLoop 显式 requeue 重试
                self._queue.requeue(tid)
                self._stats["total_failed"] += 1

        finally:
            self._release_key_lock(execution_key, key_lock)

    # ── V8.3: Business Policy Gate ──

    def _get_business_gate(self):
        """Lazy-load and cache BusinessPolicyGate (graceful degradation).

        Cached on first call — avoids creating a new gate + context builder
        + DB connections for every task evaluation.
        """
        if self._business_gate is not None:
            return self._business_gate
        try:
            from safety.business_execution_gate import BusinessPolicyGate
            self._business_gate = BusinessPolicyGate()
            return self._business_gate
        except ImportError:
            self._business_gate = False  # sentinel: unavailable
            return None

    # ── V8.5-B: Constraint Causal Memory ──

    def _get_ccm(self):
        """Lazy-load and cache ConstraintCausalMemory (graceful degradation).

        Cache pattern mirrors _get_business_gate(): None = not loaded,
        False = unavailable, otherwise cached instance.
        """
        if self._ccm is not None:
            return self._ccm
        try:
            from safety.constraint_causal_memory import ConstraintCausalMemory
            self._ccm = ConstraintCausalMemory(self._queue._db_path)
            return self._ccm
        except ImportError:
            self._ccm = False  # sentinel: unavailable
            return None

    def _ccm_bind(self, snapshot_id, task_id, binding_type, outcome):
        """Fire-and-forget CCM execution binding.

        Args:
            snapshot_id: constraint_snapshots.id (or None/falsy → skip)
            task_id: execution_queue.id
            binding_type: 'pre_execution' | 'post_execution'
            outcome: 'allowed' | 'blocked' | 'held' | 'completed' | 'failed'
        """
        if not snapshot_id:
            return
        ccm = self._get_ccm()
        if ccm is not None:
            try:
                ccm.bind_execution(snapshot_id, task_id, binding_type, outcome)
            except Exception:
                logger.debug("[WorkerLoop] CCM bind failed (non-blocking)")

    def _enqueue_hold_for_review(self, gate_result, task):
        """Create a hold-for-review notification when a task is held by the gate.

        Logs the hold and (in future) could push to a review dashboard queue.
        """
        tid = task["id"]
        task_type = task["task_type"]
        reason = gate_result.reason
        logger.info(
            "[WorkerLoop] Task %d (%s) held for review: %s",
            tid, task_type, reason,
        )

    # ── V8.2c: Side-effect isolation ──

    def _acquire_key_lock(self, execution_key):
        """Acquire per-key mutex. Returns lock (caller must release) or None/False.

        Returns:
            threading.Lock — acquired, caller must release
            False          — another worker holds this key
            None           — no key to lock (execution_key empty)
        """
        if not execution_key:
            return None
        with self._processing_locks_lock:
            if execution_key not in self._processing_locks:
                self._processing_locks[execution_key] = threading.Lock()
            lock = self._processing_locks[execution_key]
        if not lock.acquire(blocking=False):
            return False
        return lock

    @staticmethod
    def _release_key_lock(execution_key, lock):
        """Release a previously acquired key lock."""
        if lock:
            lock.release()


# ==================== ExecutionKernel（Facade） ====================

class ExecutionKernel:
    """V8 Execution Kernel 统一入口

    组合 IdempotencyGuard + WorkerLoop + DeadLetterQueue

    使用:
        kernel = ExecutionKernel()
        kernel.register_handler("send_message", my_send_fn)
        kernel.register_handler("send_quote", my_quote_fn)
        kernel.start()

        # 外部调用方:
        key = kernel.build_key(msg_id, "send_quote", order_id=42)
        if kernel.should_skip(key):
            return  # 已执行
        qid = execution_queue.enqueue("send_quote", payload)
        kernel.register_key(key, qid)
    """

    def __init__(self, queue=None, interval=5, max_retries=3):
        from execution.execution_queue import ExecutionQueue
        self.queue = queue or ExecutionQueue()
        self.guard = IdempotencyGuard()
        self.dlq = DeadLetterQueue()
        self.worker = WorkerLoop(
            queue=self.queue,
            interval=interval,
            max_retries=max_retries,
        )
        self._started = False

    def build_key(self, message_id, action_type, order_id=None, customer_id=None):
        """构建 execution_key（委托给 IdempotencyGuard）"""
        return IdempotencyGuard.build_key(message_id, action_type, order_id, customer_id)

    def build_key_from_payload(self, payload):
        """从 payload 构建 key"""
        return IdempotencyGuard.build_key_from_payload(payload)

    def should_skip(self, execution_key):
        """检查是否应跳过（委托给 IdempotencyGuard）"""
        return self.guard.should_skip(execution_key)

    def get_existing(self, execution_key):
        """获取已有执行记录"""
        return self.guard.get_existing(execution_key)

    def register_key(self, execution_key, queue_id):
        """注册 execution_key 到 queue_id"""
        return self.guard.register(execution_key, queue_id)

    def enqueue_with_guard(self, task_type, payload, priority=5, source_agent="",
                           context=None, execution_key=None):
        """带 idempotency guard 的入队（推荐使用）

        Args:
            task_type: 任务类型
            payload: 任务数据（应包含 message_id, action_type, order_id/customer_id）
            priority: 优先级
            source_agent: 来源 Agent
            context: V7 Firewall 上下文
            execution_key: 可选，不传则从 payload 自动构建

        Returns:
            int: queue_id (成功) / None (跳过或失败)
        """
        # 1. 构建/获取 execution_key
        if not execution_key:
            execution_key = IdempotencyGuard.build_key_from_payload(payload)

        # 2. Idempotency 检查
        if execution_key and self.should_skip(execution_key):
            logger.info("[Kernel] Idempotency skip %s (%s): already processed",
                        task_type, execution_key[:12])
            return None

        # 3. 确保 payload 中有 execution_key
        if execution_key:
            payload["_execution_key"] = execution_key

        # 4. 入队
        qid = self.queue.enqueue(task_type, payload, priority, source_agent, context)
        if qid and execution_key:
            self.register_key(execution_key, qid)

        return qid

    def register_handler(self, task_type, handler_fn):
        """注册任务处理器"""
        self.worker.register_handler(task_type, handler_fn)

    def register_handlers(self, handler_map):
        """批量注册处理器"""
        self.worker.register_handlers(handler_map)

    def start(self):
        """启动 worker loop"""
        if self._started:
            logger.warning("[Kernel] Already started")
            return
        self.worker.start()
        self._started = True

    def stop(self):
        """停止 worker loop"""
        self.worker.stop()
        self._started = False

    def get_stats(self):
        """获取运行统计"""
        stats = self.worker.get_stats()
        stats["queue"] = self.queue.get_queue_stats()
        return stats

    # ── V8.2d: Global Execution Audit ──

    def get_execution_audit(self, customer_id=None, task_type=None, status=None,
                            execution_key=None, limit=50):
        """全局执行审计查询

        Args:
            customer_id: 按客户筛选
            task_type: 按任务类型筛选
            status: 按状态筛选
            execution_key: 按执行 key 精确匹配
            limit: 最大返回条数（默认 50）

        Returns:
            list[dict]: 任务记录（含 trace_log 完整执行历史）
        """
        return self.queue.get_audit_log(
            customer_id=customer_id,
            task_type=task_type,
            status=status,
            execution_key=execution_key,
            limit=limit,
        )
