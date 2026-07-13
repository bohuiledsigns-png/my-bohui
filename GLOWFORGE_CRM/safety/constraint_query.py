"""V8.5-C: ConstraintQueryEngine — Causal Graph Query + Aggregation + Projection

Built on V8.5-B's constraint_snapshots + constraint_execution_bindings tables.
All methods fire-and-forget: failures return empty results + log.warning, never block.

Three layers:
  1. Query       — snapshot search with function-parameter DSL
  2. Aggregation — policy_impact, context_patterns, customer_profile
  3. Projection  — filter + group_by + metric (multi-dimensional)

Usage:
    cqe = ConstraintQueryEngine(db_path)
    results = cqe.query(verdict="BLOCK", task_type="cancel_order", since_days=7)
    impact = cqe.policy_impact("BIZ_CANCEL_001", days=30)
    proj   = cqe.project({"verdict": "BLOCK", "customer_risk__gt": 0.5}, "policy_id", "sum(order_value)")
"""

import json
import logging
import sqlite3
import time
from collections import defaultdict
from typing import Any, Optional

from safety.constraint_causal_memory import ConstraintCausalMemory

logger = logging.getLogger("glowforge.constraint_query_engine")

# Supported JSON comparison operators
_OP_MAP = {
    "gt": ">", "lt": "<", "gte": ">=", "lte": "<=",
    "eq": "=",  # explicit eq
}

# Sort column whitelist (used internally)
_ALLOWED_SORTS = {"created_at", "verdict", "task_type", "policy_count", "id", "customer_id"}


class ConstraintQueryEngine:
    """Unified entry point for constraint causal graph queries."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ccm = ConstraintCausalMemory(db_path)

    # ════════════════════════════════════════════════════════════════
    #  1. Query Layer — DSL snapshot search
    # ════════════════════════════════════════════════════════════════

    def query(self, **filters) -> list:
        """Query constraint snapshots with a function-parameter DSL.

        Supported filter keys:

            verdict=str              — "ALLOW" | "BLOCK" | "HOLD"
            task_type=str            — e.g. "cancel_order"
            customer_id=str          — exact customer ID
            satisfiable=bool         — satisfiable flag
            since_days=int           — last N days
            until_ts=float           — unix timestamp upper bound
            execution_outcome=str    — "allowed" | "blocked" | "held" | etc.

            context__<field>=val                — exact JSON match
            context__<field>__<op>=val           — JSON comparison    eq|gt|lt|gte|lte
            blocks_contains=dict                — {"policy_id": "BIZ_..."}

            limit=int  offset=int  sort=str  order=str

        Returns:
            List of deserialized snapshot dicts (see _row_to_snapshot format).
        """
        try:
            clauses, params, join_bindings = self._build_where(filters)
            sort = filters.get("sort", "created_at")
            order = filters.get("order", "desc")
            limit = filters.get("limit", 50)
            offset = filters.get("offset", 0)

            return self._ccm.query_snapshots(
                where_clauses=clauses,
                params=params,
                join_bindings=join_bindings,
                sort=sort if sort in _ALLOWED_SORTS else "created_at",
                order=order if order in ("asc", "desc") else "desc",
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            logger.warning("[CQE] query failed: %s", exc)
            return []

    # ════════════════════════════════════════════════════════════════
    #  2. Aggregation Layer
    # ════════════════════════════════════════════════════════════════

    # ── 2a. Policy Impact ──────────────────────────────────────────

    def policy_impact(self, policy_id: str, days: int = 30) -> dict:
        """Analyse constraint effect for a single policy.

        Returns:
            {
                "policy_id": str,
                "trigger_count": int,        # snapshots where policy appears in blocks/holds
                "block_count": int,          # snapshots where policy is in blocks
                "block_rate": float,
                "hold_count": int,           # snapshots where policy is in holds
                "hold_rate": float,
                "revenue_impact": float,     # SUM(order_value) from joined execution_queue
                "avg_order_value_affected": float,
                "top_contexts": [            # most frequent context patterns
                    {"context": dict, "count": int}, ...
                ],
                "estimate": bool,            # True if revenue data may be incomplete
            }
        """
        try:
            since_ts = time.time() - days * 86400
            pattern_id = f'%"{policy_id}"%'

            conn = self._ccm._get_conn()
            try:
                # Count blocks
                row = conn.execute(
                    """SELECT COUNT(*) AS cnt FROM constraint_snapshots
                       WHERE blocks_json LIKE ? AND created_at >= ?""",
                    (pattern_id, since_ts),
                ).fetchone()
                block_count = row["cnt"] if row else 0

                # Count holds
                row = conn.execute(
                    """SELECT COUNT(*) AS cnt FROM constraint_snapshots
                       WHERE holds_json LIKE ? AND created_at >= ?""",
                    (pattern_id, since_ts),
                ).fetchone()
                hold_count = row["cnt"] if row else 0

                # Count triggers (blocks OR holds)
                row = conn.execute(
                    """SELECT COUNT(*) AS cnt FROM constraint_snapshots
                       WHERE (blocks_json LIKE ? OR holds_json LIKE ?)
                       AND created_at >= ?""",
                    (pattern_id, pattern_id, since_ts),
                ).fetchone()
                trigger_count = row["cnt"] if row else 0

                # Revenue impact — block snapshots JOIN execution_queue
                revenue_impact = 0.0
                try:
                    rev = conn.execute(
                        """SELECT COALESCE(SUM(
                               CAST(
                                   json_extract(q.payload_json, '$.order_value')
                                   AS REAL
                               )
                           ), 0) AS total
                           FROM constraint_snapshots s
                           LEFT JOIN execution_queue q ON s.task_id = q.id
                           WHERE s.blocks_json LIKE ? AND s.created_at >= ?""",
                        (pattern_id, since_ts),
                    ).fetchone()
                    if rev:
                        revenue_impact = float(rev["total"])
                except Exception as rev_exc:
                    logger.debug(
                        "[CQE] policy_impact revenue join failed (table may not exist): %s",
                        rev_exc,
                    )

                # Top contexts for blocks
                ctx_rows = conn.execute(
                    """SELECT s.context_snapshot_json, COUNT(*) AS cnt
                       FROM constraint_snapshots s
                       WHERE s.blocks_json LIKE ? AND s.created_at >= ?
                       GROUP BY s.context_snapshot_json
                       ORDER BY cnt DESC LIMIT 10""",
                    (pattern_id, since_ts),
                ).fetchall()
                top_contexts = []
                for r in ctx_rows:
                    try:
                        ctx = json.loads(r["context_snapshot_json"])
                    except Exception:
                        ctx = {}
                    top_contexts.append({"context": ctx, "count": r["cnt"]})

            finally:
                conn.close()

            return {
                "policy_id": policy_id,
                "trigger_count": trigger_count,
                "block_count": block_count,
                "block_rate": round(block_count / trigger_count, 3) if trigger_count else 0.0,
                "hold_count": hold_count,
                "hold_rate": round(hold_count / trigger_count, 3) if trigger_count else 0.0,
                "revenue_impact": round(revenue_impact, 2),
                "avg_order_value_affected": round(revenue_impact / block_count, 2) if block_count else 0.0,
                "top_contexts": top_contexts,
                "estimate": True,  # revenue based on best-effort JSON extraction
            }
        except Exception as exc:
            logger.warning("[CQE] policy_impact(%s) failed: %s", policy_id, exc)
            return {"policy_id": policy_id, "error": str(exc)}

    # ── 2b. Context Pattern Mining ─────────────────────────────────

    def context_patterns(self, verdict: str = None, days: int = 30) -> list:
        """Discover frequent context patterns among constraint evaluations.

        Groups snapshots by their context_snapshot content, tallying verdict
        distribution within each group.

        Args:
            verdict: Optional verdict filter ("BLOCK" | "HOLD" | "ALLOW")
            days: Look-back window

        Returns:
            [{"pattern": dict, "count": int, "verdict_distribution": dict}, ...]
            Sorted by count descending.
        """
        try:
            filters = {"limit": 10000}
            if verdict:
                filters["verdict"] = verdict
            if days:
                filters["since_days"] = days

            snapshots = self.query(**filters)
            groups = defaultdict(lambda: {"count": 0, "verdict_distribution": defaultdict(int)})

            for s in snapshots:
                ctx = s.get("context_snapshot", {})
                # Canonical key: sort keys for consistent grouping
                key = json.dumps(ctx, sort_keys=True) if ctx else "__empty__"
                groups[key]["pattern"] = ctx
                groups[key]["count"] += 1
                groups[key]["verdict_distribution"][s.get("verdict", "UNKNOWN")] += 1

            result = []
            for g in groups.values():
                g["verdict_distribution"] = dict(g["verdict_distribution"])
                result.append(g)

            result.sort(key=lambda x: x["count"], reverse=True)
            return result
        except Exception as exc:
            logger.warning("[CQE] context_patterns failed: %s", exc)
            return []

    # ── 2c. Customer Constraint Profile ───────────────────────────

    def customer_profile(self, customer_id: str) -> dict:
        """Build a constraint profile for a single customer.

        Returns:
            {
                "customer_id": str,
                "total_evaluations": int,
                "by_verdict": {"ALLOW": int, "BLOCK": int, "HOLD": int},
                "by_task_type": {"cancel_order": int, ...},
                "top_blocking_policies": [{"policy_id": str, "count": int}, ...],
                "risk_trend": [{"period": str, "block_count": int, "hold_count": int}, ...],
            }
        """
        try:
            snapshots = self.query(customer_id=customer_id, limit=10000)

            total = len(snapshots)
            by_verdict: dict = defaultdict(int)
            by_task_type: dict = defaultdict(int)
            blocking_policies: dict = defaultdict(int)

            # Time-series buckets (by day, last 14 days)
            now = time.time()
            day_buckets: dict = defaultdict(lambda: {"block_count": 0, "hold_count": 0})

            for s in snapshots:
                verdict = s.get("verdict", "UNKNOWN")
                by_verdict[verdict] += 1
                by_task_type[s.get("task_type", "")] += 1

                if verdict == "BLOCK":
                    for b in s.get("blocks", []):
                        blocking_policies[b.get("policy_id", "UNKNOWN")] += 1

                # Day bucket for risk trend
                created = s.get("created_at", 0)
                if created >= now - 14 * 86400:
                    day_label = time.strftime("%Y-%m-%d", time.localtime(created))
                    if verdict == "BLOCK":
                        day_buckets[day_label]["block_count"] += 1
                    elif verdict == "HOLD":
                        day_buckets[day_label]["hold_count"] += 1

            top_blocking = sorted(blocking_policies.items(), key=lambda x: -x[1])[:10]
            risk_trend = [
                {"period": k, "block_count": v["block_count"], "hold_count": v["hold_count"]}
                for k, v in sorted(day_buckets.items())
            ]

            return {
                "customer_id": customer_id,
                "total_evaluations": total,
                "by_verdict": dict(by_verdict),
                "by_task_type": dict(by_task_type),
                "top_blocking_policies": [
                    {"policy_id": pid, "count": cnt} for pid, cnt in top_blocking
                ],
                "risk_trend": risk_trend,
            }
        except Exception as exc:
            logger.warning("[CQE] customer_profile(%s) failed: %s", customer_id, exc)
            return {"customer_id": customer_id, "error": str(exc)}

    # ════════════════════════════════════════════════════════════════
    #  3. Projection Layer — filter + group_by + metric
    # ════════════════════════════════════════════════════════════════

    def project(
        self,
        filter: dict,
        group_by: str = "policy_id",
        metric: str = "sum(order_value)",
        days: int = 30,
        limit: int = 10,
    ) -> list:
        """Multi-dimensional projection: filter → group_by → metric.

        Answers questions like "which policies most frequently BLOCK
        high-risk orders" in a single call.

        Args:
            filter: Query filter dict (same keys as query() kwargs)
            group_by: "policy_id" (via json_each on blocks_json) OR
                      a direct column name (verdict, task_type, etc.)
            metric: "sum(order_value)" — aggregates from execution_queue
                    via s.task_id JOIN.
            days: Look-back window (overridden by filter.since_days if present)
            limit: Max result rows

        Returns:
            [{"<group_by>": value, "count": int, "total_revenue_affected": float}, ...]
        """
        try:
            since_ts = time.time() - days * 86400

            # Merge days into filter dict
            f = dict(filter)
            if "since_days" not in f:
                f["since_days"] = days

            # If group_by is "policy_id", use json_each to expand blocks array
            if group_by == "policy_id":
                return self._project_by_policy(f, since_ts, limit)
            else:
                return self._project_by_column(f, group_by, metric, since_ts, limit)
        except Exception as exc:
            logger.warning("[CQE] project failed: %s", exc)
            return []

    # ════════════════════════════════════════════════════════════════
    #  Internal helpers
    # ════════════════════════════════════════════════════════════════

    def _build_where(self, filters: dict, alias: str = "constraint_snapshots") -> tuple:
        """Build (clauses, params, join_bindings) from filter dict.

        Each filter key maps to one SQL WHERE clause fragment.
        clauses and params are parallel lists for parameterized SQL.

        Args:
            filters: The filter dict (query kwargs or project filter dict)
            alias: Table alias prefix for column references.
                   Default "constraint_snapshots" for direct table references.
                   Use "s" when the table is aliased (project/policy_impact).
        """
        clauses: list = []
        params: list = []
        join_bindings = False

        for key, value in filters.items():
            if key in ("verdict", "task_type"):
                clauses.append(f"{alias}.{key} = ?")
                params.append(value)

            elif key == "customer_id":
                clauses.append(f"{alias}.customer_id = ?")
                params.append(str(value))

            elif key == "satisfiable":
                clauses.append(f"{alias}.satisfiable = ?")
                params.append(1 if value else 0)

            elif key == "since_days":
                threshold = time.time() - int(value) * 86400
                clauses.append(f"{alias}.created_at >= ?")
                params.append(threshold)

            elif key == "until_ts":
                clauses.append(f"{alias}.created_at <= ?")
                params.append(float(value))

            elif key == "execution_outcome":
                join_bindings = True
                clauses.append("b.execution_outcome = ?")
                params.append(value)

            elif key == "blocks_contains" and isinstance(value, dict):
                for k, v in value.items():
                    clauses.append(f"{alias}.blocks_json LIKE ?")
                    params.append(f'%"{k}": "{v}"%')

            elif key == "holds_contains" and isinstance(value, dict):
                for k, v in value.items():
                    clauses.append(f"{alias}.holds_json LIKE ?")
                    params.append(f'%"{k}": "{v}"%')

            elif key.startswith("context__"):
                # Pattern: context__<field>[__<op>]
                #   context__order_status="in_production"         → eq
                #   context__customer_risk__gt=0.6               → gt
                parts = key.split("__")
                if len(parts) >= 2:
                    field = parts[1]
                    op = _OP_MAP.get(parts[2], "=") if len(parts) >= 3 else "="
                    clauses.append(
                        f"json_extract({alias}.context_snapshot_json,"
                        f" '$.{field}') {op} ?"
                    )
                    params.append(value)

            # Skip control keys handled elsewhere
            elif key in ("limit", "offset", "sort", "order"):
                pass

            else:
                logger.debug("[CQE] Unrecognised filter key: %s", key)

        return clauses, params, join_bindings

    def _project_by_policy(self, filter: dict, since_ts: float, limit: int) -> list:
        """Projection grouped by policy_id (expanded from blocks_json via json_each)."""
        clauses, params, _ = self._build_where(filter, alias="s")

        conn = self._ccm._get_conn()
        try:
            where_sql = " AND ".join(clauses) if clauses else "1=1"
            # Also add time filter
            full_where = f"{where_sql} AND s.created_at >= ?"
            full_params = params + [since_ts]

            sql = f"""
                SELECT
                    json_extract(b.value, '$.policy_id') AS policy_id,
                    COUNT(*) AS count,
                    COALESCE(SUM(
                        CAST(json_extract(q.payload_json, '$.order_value') AS REAL)
                    ), 0) AS total_revenue_affected
                FROM constraint_snapshots s
                JOIN json_each(s.blocks_json) AS b
                LEFT JOIN execution_queue q ON s.task_id = q.id
                WHERE {full_where}
                GROUP BY policy_id
                ORDER BY count DESC
                LIMIT ?
            """
            full_params.append(limit)
            rows = conn.execute(sql, full_params).fetchall()
            return [
                {
                    "policy_id": r["policy_id"],
                    "count": r["count"],
                    "total_revenue_affected": round(float(r["total_revenue_affected"]), 2),
                }
                for r in rows
            ]
        finally:
            conn.close()

    def _project_by_column(self, filter: dict, group_by: str,
                           metric: str, since_ts: float, limit: int) -> list:
        """Projection grouped by a direct column (not policy_id)."""
        # Whitelist group_by
        allowed_columns = {"verdict", "task_type", "customer_id"}
        if group_by not in allowed_columns:
            logger.warning("[CQE] Unsupported group_by column: %s", group_by)
            return []

        clauses, params, _ = self._build_where(filter, alias="s")

        conn = self._ccm._get_conn()
        try:
            where_sql = " AND ".join(clauses) if clauses else "1=1"
            full_where = f"{where_sql} AND s.created_at >= ?"
            full_params = params + [since_ts]

            if "sum(" in metric.lower() and "order_value" in metric.lower():
                metric_sql = (
                    "COALESCE(SUM("
                    "CAST(json_extract(q.payload_json, '$.order_value') AS REAL)"
                    "), 0)"
                )
            else:
                metric_sql = "COUNT(*)"

            sql = f"""
                SELECT
                    s.{group_by} AS group_value,
                    COUNT(*) AS count,
                    {metric_sql} AS total_revenue_affected
                FROM constraint_snapshots s
                LEFT JOIN execution_queue q ON s.task_id = q.id
                WHERE {full_where}
                GROUP BY s.{group_by}
                ORDER BY count DESC
                LIMIT ?
            """
            full_params.append(limit)
            rows = conn.execute(sql, full_params).fetchall()
            return [
                {
                    group_by: r["group_value"],
                    "count": r["count"],
                    "total_revenue_affected": round(float(r["total_revenue_affected"]), 2),
                }
                for r in rows
            ]
        finally:
            conn.close()
