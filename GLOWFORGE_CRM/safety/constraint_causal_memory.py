"""V8.5-B: ConstraintCausalMemory — Constraint Causal Memory Layer

Persists constraint snapshots and execution bindings to create an auditable
chain: constraint_set -> gate_result -> execution -> outcome.

All snapshot writes are fire-and-forget: failures are logged but never
propagated. This layer must never block business logic.
"""

import json
import logging
import sqlite3
import time
from typing import Optional

logger = logging.getLogger("glowforge.constraint_causal_memory")


class ConstraintCausalMemory:
    """Records and queries constraint snapshots and execution bindings.

    Two-layer persistence:
      1. constraint_snapshots  — full ConstraintSet at evaluation time
      2. constraint_execution_bindings — snapshot → execution → outcome links

    Usage:
        ccm = ConstraintCausalMemory(db_path)
        sid = ccm.record_snapshot(gate_result, task_id=42, customer_id="1", task_type="cancel_order")
        ccm.bind_execution(sid, 42, "pre_execution", "blocked")
        chain = ccm.get_causal_chain(42)
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    # ── Internal helpers ──

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── Write operations (fire-and-forget) ──

    def record_snapshot(
        self,
        gate_result,
        task_id: Optional[int] = None,
        customer_id: str = "",
        task_type: str = "",
    ) -> Optional[int]:
        """Persist a GateResult's constraint set as a snapshot row.

        Args:
            gate_result: GateResult instance with .constraints, .verdict,
                         .reason, .context_snapshot, .satisfiable
            task_id: FK to execution_queue.id (None for ad-hoc evaluations)
            customer_id: Customer identifier for customer-scoped queries
            task_type: The action being evaluated (e.g. 'cancel_order')

        Returns:
            snapshot_id (int) on success, None on failure
        """
        try:
            # Serialize constraint set to JSON-safe dicts
            constraint_dict = {}
            if gate_result.constraints is not None:
                try:
                    constraint_dict = gate_result.constraints.to_dict(max_per_type=50)
                except Exception:
                    pass

            blocks_json = json.dumps(constraint_dict.get("blocks", []), ensure_ascii=False)
            holds_json = json.dumps(constraint_dict.get("holds", []), ensure_ascii=False)
            allows_json = json.dumps(constraint_dict.get("allows", []), ensure_ascii=False)
            satisfiable = constraint_dict.get("satisfiable", gate_result.satisfiable)
            reason = constraint_dict.get("reason", gate_result.reason)
            verdict = constraint_dict.get("verdict", gate_result.verdict)
            blocks = constraint_dict.get("blocks", [])
            holds = constraint_dict.get("holds", [])
            allows = constraint_dict.get("allows", [])
            policy_count = len(blocks) + len(holds) + len(allows)

            context_json = json.dumps(
                getattr(gate_result, "context_snapshot", {}),
                ensure_ascii=False,
            )

            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """INSERT INTO constraint_snapshots
                       (task_id, customer_id, task_type, verdict, reason,
                        satisfiable, blocks_json, holds_json, allows_json,
                        policy_count, context_snapshot_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task_id,
                        str(customer_id) if customer_id is not None else "",
                        task_type or "",
                        str(verdict) if verdict else "ALLOW",
                        str(reason) if reason else "",
                        1 if satisfiable else 0,
                        blocks_json,
                        holds_json,
                        allows_json,
                        policy_count,
                        context_json,
                        time.time(),
                    ),
                )
                snapshot_id = cursor.lastrowid
                conn.commit()
                return snapshot_id
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] record_snapshot failed (task_id=%s): %s", task_id, exc)
            return None

    def bind_execution(
        self,
        snapshot_id: int,
        task_id: int,
        binding_type: str,
        outcome: str,
    ) -> Optional[int]:
        """Record a binding between a snapshot and an execution outcome.

        Args:
            snapshot_id: FK to constraint_snapshots.id
            task_id: FK to execution_queue.id
            binding_type: 'pre_execution' | 'post_execution' | 're_evaluation'
            outcome: 'allowed' | 'blocked' | 'held' | 'completed' | 'failed'

        Returns:
            binding_id (int) on success, None on failure
        """
        try:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """INSERT INTO constraint_execution_bindings
                       (snapshot_id, task_id, binding_type, execution_outcome, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (snapshot_id, task_id, binding_type, outcome, time.time()),
                )
                binding_id = cursor.lastrowid
                conn.commit()
                return binding_id
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(
                "[CCM] bind_execution failed (snapshot=%s task=%s): %s",
                snapshot_id, task_id, exc,
            )
            return None

    # ── Read operations ──

    def get_snapshot(self, snapshot_id: int) -> Optional[dict]:
        """Retrieve a single snapshot with deserialized constraint arrays."""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM constraint_snapshots WHERE id = ?",
                    (snapshot_id,),
                ).fetchone()
                return self._row_to_snapshot(row) if row else None
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] get_snapshot(%s) failed: %s", snapshot_id, exc)
            return None

    def get_snapshots_by_task(self, task_id: int) -> list:
        """Return all snapshots associated with a task, newest first."""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM constraint_snapshots
                       WHERE task_id = ? ORDER BY created_at DESC""",
                    (task_id,),
                ).fetchall()
                return [self._row_to_snapshot(r) for r in rows]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] get_snapshots_by_task(%s) failed: %s", task_id, exc)
            return []

    def get_snapshots_by_customer(self, customer_id: str, limit: int = 50) -> list:
        """Return snapshots for a customer, newest first."""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM constraint_snapshots
                       WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?""",
                    (customer_id, limit),
                ).fetchall()
                return [self._row_to_snapshot(r) for r in rows]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] get_snapshots_by_customer(%s) failed: %s", customer_id, exc)
            return []

    def get_snapshots_by_time_range(
        self, start_ts: float, end_ts: float, limit: int = 100
    ) -> list:
        """Return snapshots within a time window, newest first."""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM constraint_snapshots
                       WHERE created_at >= ? AND created_at <= ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (start_ts, end_ts, limit),
                ).fetchall()
                return [self._row_to_snapshot(r) for r in rows]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] get_snapshots_by_time_range failed: %s", exc)
            return []

    def get_causal_chain(self, task_id: int) -> list:
        """Return the full causal chain for a task: snapshots + bindings.

        Returns a list of dicts, each containing:
            - snapshot: deserialized snapshot dict
            - bindings: list of binding dicts for this snapshot

        Ordered chronologically (oldest first) to show the progression
        of gate evaluations over time.
        """
        try:
            conn = self._get_conn()
            try:
                snapshots = conn.execute(
                    """SELECT * FROM constraint_snapshots
                       WHERE task_id = ? ORDER BY created_at ASC""",
                    (task_id,),
                ).fetchall()

                result = []
                for s in snapshots:
                    bindings = conn.execute(
                        """SELECT * FROM constraint_execution_bindings
                           WHERE snapshot_id = ? ORDER BY created_at ASC""",
                        (s["id"],),
                    ).fetchall()
                    result.append({
                        "snapshot": self._row_to_snapshot(s),
                        "bindings": [dict(b) for b in bindings],
                    })
                return result
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] get_causal_chain(%s) failed: %s", task_id, exc)
            return []

    # ── Generic query — used by ConstraintQueryEngine internally ──

    def query_snapshots(
        self,
        where_clauses: list,
        params: list,
        join_bindings: bool = False,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Generic WHERE query — called by ConstraintQueryEngine, not exposed to callers.

        Args:
            where_clauses: SQL clause strings (without "WHERE" prefix)
            params: Parameter values for each clause
            join_bindings: If True, LEFT JOIN constraint_execution_bindings
            sort: Sort column (whitelisted for safety)
            order: "asc" or "desc"
            limit: Max rows
            offset: Row offset

        Returns:
            List of deserialized snapshot dicts, empty on failure
        """
        try:
            # Whitelist sort column to prevent injection
            _ALLOWED_SORTS = {"created_at", "verdict", "task_type", "policy_count", "id", "customer_id"}
            if sort not in _ALLOWED_SORTS:
                sort = "created_at"
            if order.lower() not in ("asc", "desc"):
                order = "desc"

            conn = self._get_conn()
            try:
                join_sql = ""
                if join_bindings:
                    join_sql = (
                        " LEFT JOIN constraint_execution_bindings b"
                        " ON constraint_snapshots.id = b.snapshot_id"
                    )

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                sql = (
                    f"SELECT DISTINCT constraint_snapshots.*"
                    f" FROM constraint_snapshots{join_sql}"
                    f" WHERE {where_sql}"
                    f" ORDER BY constraint_snapshots.{sort} {order}"
                    f" LIMIT ? OFFSET ?"
                )
                all_params = list(params) + [limit, offset]
                rows = conn.execute(sql, all_params).fetchall()
                return [self._row_to_snapshot(r) for r in rows]
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("[CCM] query_snapshots failed: %s", exc)
            return []

    # ── Internal: row → dict conversion ──

    @staticmethod
    def _row_to_snapshot(row) -> dict:
        """Convert a snapshot DB row to a fully deserialized dict."""
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "customer_id": row["customer_id"],
            "task_type": row["task_type"],
            "verdict": row["verdict"],
            "reason": row["reason"],
            "satisfiable": bool(row["satisfiable"]),
            "blocks": json.loads(row["blocks_json"]),
            "holds": json.loads(row["holds_json"]),
            "allows": json.loads(row["allows_json"]),
            "policy_count": row["policy_count"],
            "context_snapshot": json.loads(row["context_snapshot_json"]),
            "created_at": row["created_at"],
        }
