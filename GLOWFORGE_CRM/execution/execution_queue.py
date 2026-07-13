"""ExecutionQueue — 持久化 DB 任务队列

所有执行动作的唯一入口。双层 V7 Firewall 集成：
1. 入队时检查 (enqueue) → BLOCK 不入队
2. 执行前检查 (recheck_firewall) → BLOCK 标记失败
"""
import json
import logging
import os
import sqlite3
import threading
import time
import uuid

logger = logging.getLogger("glowforge.execution_queue")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 模块级锁，确保同一时间只有一个 dequeue 操作修改 DB
_dequeue_lock = threading.Lock()


class ExecutionQueue:
    """DB-backed persistent execution queue with V7 firewall integration"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH
        self._firewall = None
        self._firewall_lock = threading.Lock()

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _get_firewall(self):
        """Lazy-load V7 ExecutionFirewall"""
        if self._firewall is None:
            with self._firewall_lock:
                if self._firewall is None:
                    try:
                        from safety.execution_firewall import ExecutionFirewall
                        self._firewall = ExecutionFirewall()
                    except ImportError:
                        self._firewall = False  # sentinel: unavailable
        return self._firewall if self._firewall is not False else None

    def _build_decision_id(self):
        return f"v8_{uuid.uuid4().hex[:12]}"

    # ── V8.2: Execution Trace ──

    @staticmethod
    def _append_trace(conn, queue_id, event, detail=""):
        """Append a trace entry to execution_queue.trace_log (JSON array)."""
        try:
            row = conn.execute(
                "SELECT trace_log FROM execution_queue WHERE id=?", (queue_id,)
            ).fetchone()
            if row is None:
                return
            existing = row["trace_log"]
            traces = json.loads(existing) if existing else []
            traces.append({
                "t": time.time(),
                "event": event,
                "detail": detail[:200],
            })
            conn.execute(
                "UPDATE execution_queue SET trace_log=? WHERE id=?",
                (json.dumps(traces, ensure_ascii=False), queue_id),
            )
        except Exception:
            pass

    # ── Public API ──

    def enqueue(self, task_type, payload, priority=5, source_agent="", context=None):
        """Enqueue a task. Passes through V7 Firewall. Returns queue_id or None.

        Args:
            task_type: e.g. 'send_message', 'send_quote', 'update_crm'
            payload: dict with task data (customer_id, content, price, etc.)
            priority: 1 (highest) ~ 10 (lowest), default 5
            source_agent: agent ID requesting enqueue
            context: dict passed to V7 Firewall for environment context

        Returns:
            int: queue_id on success
            None: if firewall blocks or DB error
        """
        firewall = self._get_firewall()
        customer_id = payload.get("customer_id")
        firewall_verdict = ""

        if firewall and customer_id:
            try:
                action = dict(payload)
                action["type"] = task_type
                action["source_agent"] = source_agent or "execution_queue"
                ctx = dict(context or {})
                decision = firewall.check(customer_id, action, ctx)
                firewall_verdict = decision.get("verdict", "ALLOW")
                if firewall_verdict == "BLOCK":
                    logger.info(
                        "[Queue] Firewall BLOCKED enqueue %s for customer %s: %s",
                        task_type, customer_id, decision.get("reason", ""),
                    )
                    return None
            except Exception as e:
                logger.warning("[Queue] Firewall check failed (allowing): %s", e)
                firewall_verdict = "ALLOW"

        try:
            conn = self._get_conn()
            cur = conn.execute(
                """INSERT INTO execution_queue
                   (task_type, payload_json, priority, source_agent, firewall_verdict)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_type, json.dumps(payload, ensure_ascii=False), priority,
                 source_agent, firewall_verdict),
            )
            qid = cur.lastrowid
            conn.commit()

            # V8.2: execution trace
            if qid:
                self._append_trace(conn, qid, "enqueued", task_type)
                conn.commit()

            conn.close()
            logger.debug("[Queue] Enqueued %s id=%d prio=%d", task_type, qid, priority)
            return qid
        except Exception as e:
            logger.error("[Queue] enqueue failed: %s", e)
            return None

    def dequeue(self, worker_id, batch_size=1):
        """Atomically dequeue pending tasks using optimistic locking.

        Uses UPDATE...WHERE status='pending' AND locked_at=0 to avoid
        concurrent worker conflicts. Returns list of task dicts.
        """
        with _dequeue_lock:
            try:
                conn = self._get_conn()
                try:
                    now = time.time()
                    rows = conn.execute(
                        """UPDATE execution_queue
                           SET status='processing', locked_at=?, locked_by=?, updated_at=CURRENT_TIMESTAMP
                           WHERE id IN (
                               SELECT id FROM execution_queue
                               WHERE status='pending' AND locked_at=0
                               ORDER BY priority ASC, created_at ASC
                               LIMIT ?
                           )
                           RETURNING *""",
                        (now, worker_id, batch_size),
                    ).fetchall()
                    for r in rows:
                        self._append_trace(conn, r["id"], "dequeued", worker_id)
                    conn.commit()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
            except Exception as e:
                logger.error("[Queue] dequeue failed: %s", e)
                return []

    def complete(self, queue_id, result=None):
        """Mark task as completed with optional result dict."""
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE execution_queue
                       SET status='completed', result_json=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (json.dumps(result or {}, ensure_ascii=False), queue_id),
                )
                self._append_trace(conn, queue_id, "completed")
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Queue] complete failed id=%d: %s", queue_id, e)
            return False

    def fail(self, queue_id, error=""):
        """V8.2: Pure state setter — increment retry, set status='failed'.

        NEVER re-pends (doesn't set status='pending'). WorkerLoop is the
        sole retry controller — it calls fail(), then decides to requeue()
        or DLQ.  DB stores state; Worker controls behavior.
        """
        try:
            conn = self._get_conn()
            try:
                retry = conn.execute(
                    "SELECT COALESCE(retry_count, 0) + 1 FROM execution_queue WHERE id=?",
                    (queue_id,),
                ).fetchone()
                if not retry:
                    return False
                retry_count = retry[0]
                conn.execute(
                    """UPDATE execution_queue
                       SET status='failed', retry_count=?, error=?,
                           locked_at=0, locked_by='',
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (retry_count, error[:500], queue_id),
                )
                self._append_trace(conn, queue_id, "failed", error[:200])
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Queue] fail failed id=%d: %s", queue_id, e)
            return False

    def requeue(self, queue_id, delay_seconds=0):
        """Re-queue a task (reset to pending with optional delay)."""
        try:
            conn = self._get_conn()
            try:
                if delay_seconds > 0:
                    from datetime import datetime, timedelta
                    scheduled = (datetime.now() + timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        """UPDATE execution_queue
                           SET status='pending', locked_at=0, locked_by='',
                               scheduled_at=?, updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (scheduled, queue_id),
                    )
                else:
                    conn.execute(
                        """UPDATE execution_queue
                           SET status='pending', locked_at=0, locked_by='',
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (queue_id,),
                    )
                self._append_trace(conn, queue_id, "requeued",
                                   f"delay={delay_seconds}s")
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Queue] requeue failed id=%d: %s", queue_id, e)
            return False

    # ── V8.3: HOLD / Release / Count ──

    def set_hold(self, queue_id, reason=""):
        """Set a task to HOLD_FOR_REVIEW status.

        Args:
            queue_id: task ID
            reason: human-readable reason for the hold

        Returns:
            bool: True on success
        """
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE execution_queue
                       SET status='hold', hold_reason=?,
                           locked_at=0, locked_by='',
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (reason[:500], queue_id),
                )
                self._append_trace(conn, queue_id, "hold", reason[:200])
                conn.commit()
                logger.info("[Queue] Task %d set to HOLD: %s", queue_id, reason[:100])
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Queue] set_hold failed id=%d: %s", queue_id, e)
            return False

    def release_hold(self, queue_id):
        """Release a held task back to pending for execution.

        Args:
            queue_id: task ID

        Returns:
            bool: True on success
        """
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE execution_queue
                       SET status='pending', hold_reason='',
                           locked_at=0, locked_by='',
                       updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND status='hold'""",
                    (queue_id,),
                )
                self._append_trace(conn, queue_id, "released_from_hold")
                conn.commit()
                logger.info("[Queue] Task %d released from HOLD", queue_id)
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error("[Queue] release_hold failed id=%d: %s", queue_id, e)
            return False

    def count_held(self):
        """Count tasks currently in HOLD_FOR_REVIEW status.

        Returns:
            int: number of held tasks
        """
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM execution_queue WHERE status='hold'"
                ).fetchone()
                return row["c"] if row else 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[Queue] count_held failed: %s", e)
            return 0

    def recheck_firewall(self, queue_id):
        """Re-check V7 Firewall before execution. Returns verdict string."""
        firewall = self._get_firewall()
        if firewall is None:
            return "ALLOW"

        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM execution_queue WHERE id=?", (queue_id,)
            ).fetchone()
            conn.close()
            if not row:
                return "ALLOW"

            payload = json.loads(row["payload_json"] or "{}")
            customer_id = payload.get("customer_id")
            if not customer_id:
                return "ALLOW"

            action = dict(payload)
            action["type"] = row["task_type"]
            action["source_agent"] = row["source_agent"] or "execution_engine"

            decision = firewall.check(customer_id, action, {})
            verdict = decision.get("verdict", "ALLOW")
            if verdict == "BLOCK":
                logger.info(
                    "[Queue] Firewall recheck BLOCKED task %d (%s): %s",
                    queue_id, row["task_type"], decision.get("reason", ""),
                )
                self.fail(queue_id, "V7 firewall blocked at execution time")
            return verdict
        except Exception as e:
            logger.warning("[Queue] recheck_firewall failed (allowing): %s", e)
            return "ALLOW"

    def cleanup_stale_locks(self, timeout=300):
        """Recover tasks stuck in 'processing' with stale locks."""
        try:
            conn = self._get_conn()
            try:
                stale_cutoff = time.time() - timeout
                rows = conn.execute(
                    """UPDATE execution_queue
                       SET status='pending', locked_at=0, locked_by='',
                           updated_at=CURRENT_TIMESTAMP
                       WHERE status='processing' AND locked_at > 0 AND locked_at < ?
                       RETURNING id""",
                    (stale_cutoff,),
                ).fetchall()
                conn.commit()
                if rows:
                    logger.info("[Queue] Cleaned %d stale locks", len(rows))
                return len(rows)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[Queue] cleanup_stale_locks failed: %s", e)
            return 0

    def get_queue_stats(self):
        """Return queue stats by status."""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as c FROM execution_queue GROUP BY status"
                ).fetchall()
                return {r["status"]: r["c"] for r in rows}
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[Queue] get_queue_stats failed: %s", e)
            return {}

    def get_pending_count(self):
        """Quick count of pending tasks."""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM execution_queue WHERE status='pending'"
                ).fetchone()
                return row["c"]
            finally:
                conn.close()
        except Exception:
            return 0

    # ── V8.2d: Execution Audit ──

    def get_audit_log(self, customer_id=None, task_type=None, status=None,
                      execution_key=None, limit=50):
        """Query execution history with optional filters. Returns trace_log."""
        try:
            conn = self._get_conn()
            try:
                clauses = []
                params = []

                if customer_id is not None:
                    # Escape LIKE wildcards to prevent injection
                    safe = str(customer_id).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    clauses.append("payload_json LIKE ? ESCAPE '\\'")
                    params.append(f'%"customer_id": {safe}%')
                if task_type:
                    clauses.append("task_type = ?")
                    params.append(task_type)
                if status:
                    clauses.append("status = ?")
                    params.append(status)
                if execution_key:
                    clauses.append("execution_key = ?")
                    params.append(execution_key)

                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                sql = (
                    "SELECT id, task_type, status, retry_count, execution_key, "
                    "       error, trace_log, created_at, updated_at, "
                    "       source_agent, priority "
                    f"FROM execution_queue{where} "
                    "ORDER BY id DESC LIMIT ?"
                )
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()

            result = []
            for r in rows:
                d = dict(r)
                # Parse trace_log for convenience
                try:
                    d["trace"] = json.loads(d.get("trace_log") or "[]")
                except Exception:
                    d["trace"] = []
                result.append(d)
            return result
        except Exception as e:
            logger.error("[Queue] get_audit_log failed: %s", e)
            return []
