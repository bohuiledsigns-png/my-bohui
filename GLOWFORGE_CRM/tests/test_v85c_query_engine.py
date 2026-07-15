"""V8.5-C: Constraint Query Engine — full verification suite.

Tests all 3 layers: Query, Aggregation, Projection.
Telemetry context: session built on V8.5-B causal memory capture.

Usage:
    python -m pytest tests/test_v85c_query_engine.py -v
    # or
    python tests/test_v85c_query_engine.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import init_db, init_v85b_tables
from safety.constraint_causal_memory import ConstraintCausalMemory
from safety.constraint_query import ConstraintQueryEngine


def _seed_data(db_path: str):
    """Insert test data into V8.5-B tables for CQE queries.

    Creates 3 policies, 5 customers, and a mix of BLOCK/HOLD/ALLOW snapshots
    with realistic context, then binds execution outcomes.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure execution_queue table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payload_json TEXT NOT NULL DEFAULT '{}',
            execution_key TEXT,
            trace_log TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            handler_name TEXT,
            priority INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0
        )
    """)

    # Insert some execution tasks with realistic order values
    tasks = [
        (1, "cancel_order", '{"customer_id": "C001", "order_value": 1500.00, "order_status": "in_production"}'),
        (2, "cancel_order", '{"customer_id": "C001", "order_value": 800.00, "order_status": "pending"}'),
        (3, "modify_order", '{"customer_id": "C002", "order_value": 2500.00, "order_status": "in_production"}'),
        (4, "cancel_order", '{"customer_id": "C003", "order_value": 500.00, "order_status": "shipped"}'),
        (5, "price_change", '{"customer_id": "C002", "order_value": 3200.00}'),
        (6, "cancel_order", '{"customer_id": "C001", "order_value": 12000.00, "order_status": "in_production"}'),
    ]
    now = time.time()
    for tid, ttype, payload in tasks:
        conn.execute(
            """INSERT INTO execution_queue (id, task_type, status, payload_json, created_at, updated_at)
               VALUES (?, ?, 'completed', ?, ?, ?)""",
            (tid, ttype, payload, now - 3600, now),
        )

    # Insert snapshots (BLOCK, HOLD, ALLOW mix across customers)
    snapshots = [
        # task_id=1 (C001, cancel_order, 1500, in_production) — BLOCK by BIZ_CANCEL_001
        (1, "C001", "cancel_order", "BLOCK",
         "BIZ_CANCEL_001: order in production",
         '[{"policy_id": "BIZ_CANCEL_001", "verdict": "BLOCK", "reason": "order in production", "severity": "error", "priority": 90}]',
         '[]', '[]',
         '{"order_status": "in_production", "production_stage": "cutting", "customer_risk": 0.3}',
         now - 10 * 86400),

        # task_id=2 (C001, cancel_order, 800, pending) — HOLD by BIZ_CANCEL_001
        (2, "C001", "cancel_order", "HOLD",
         "BIZ_CANCEL_001: high-value cancellation review",
         '[]',
         '[{"policy_id": "BIZ_CANCEL_001", "verdict": "HOLD", "reason": "high-value review", "severity": "warning", "priority": 60}]',
         '[]',
         '{"order_status": "pending", "customer_risk": 0.3}',
         now - 8 * 86400),

        # task_id=3 (C002, modify_order, 2500, in_production) — BLOCK by BIZ_MODIFY_001
        (3, "C002", "modify_order", "BLOCK",
         "BIZ_MODIFY_001: modification not allowed in production",
         '[{"policy_id": "BIZ_MODIFY_001", "verdict": "BLOCK", "reason": "modification not allowed in production", "severity": "error", "priority": 90}]',
         '[]', '[]',
         '{"order_status": "in_production", "production_stage": "assembly", "customer_risk": 0.5}',
         now - 5 * 86400),

        # task_id=4 (C003, cancel_order, 500, shipped) — BLOCK by BIZ_CANCEL_001
        (4, "C003", "cancel_order", "BLOCK",
         "BIZ_CANCEL_001: order already shipped",
         '[{"policy_id": "BIZ_CANCEL_001", "verdict": "BLOCK", "reason": "order already shipped", "severity": "error", "priority": 95}]',
         '[]', '[]',
         '{"order_status": "shipped", "lead_state": "CLOSED_WON", "customer_risk": 0.1}',
         now - 3 * 86400),

        # task_id=5 (C002, price_change, 3200) — ALLOW
        (5, "C002", "price_change", "ALLOW",
         "",
         '[]', '[]',
         '[{"policy_id": "BIZ_PRICE_001", "verdict": "ALLOW", "reason": "", "severity": "info", "priority": 30}]',
         '{"customer_risk": 0.5, "lead_state": "NEGOTIATION"}',
         now - 2 * 86400),

        # task_id=6 (C001, cancel_order, 12000, in_production) — BLOCK by BIZ_CANCEL_001 (high value)
        (6, "C001", "cancel_order", "BLOCK",
         "BIZ_CANCEL_001: order in production + high value",
         '[{"policy_id": "BIZ_CANCEL_001", "verdict": "BLOCK", "reason": "high-value order in production", "severity": "error", "priority": 95}]',
         '[]', '[]',
         '{"order_status": "in_production", "production_stage": "cutting", "customer_risk": 0.7}',
         now - 1 * 86400),

        # No task — ad-hoc ALLOW (customer constraint profile test)
        (None, "C001", "cancel_order", "ALLOW",
         "",
         '[]', '[]',
         '[{"policy_id": "BIZ_CANCEL_001", "verdict": "ALLOW", "reason": "", "severity": "info", "priority": 30}]',
         '{"order_status": "pending", "customer_risk": 0.2}',
         now - 12 * 86400),
    ]

    conn.commit()
    conn.close()

    ccm = ConstraintCausalMemory(db_path)
    snapshot_ids = []
    for s in snapshots:
        sid = ccm.record_snapshot(
            _MockGateResult(
                constraints=_MockConstraintSet(
                    blocks=json.loads(s[5]) if isinstance(s[5], str) else [],
                    holds=json.loads(s[6]) if isinstance(s[6], str) else [],
                    allows=json.loads(s[7]) if isinstance(s[7], str) else [],
                    verdict=s[3],
                    reason=s[4],
                ),
                verdict=s[3],
                reason=s[4],
                context_snapshot=json.loads(s[8]) if isinstance(s[8], str) else s[8] if isinstance(s[8], dict) else {},
            ),
            task_id=s[0],
            customer_id=s[1],
            task_type=s[2],
        )
        if sid is not None:
            snapshot_ids.append(sid)

    # Bind execution outcomes
    bindings = [
        (snapshot_ids[0], 1, "pre_execution", "blocked"),    # task 1 BLOCK
        (snapshot_ids[1], 2, "pre_execution", "held"),       # task 2 HOLD
        (snapshot_ids[2], 3, "pre_execution", "blocked"),    # task 3 BLOCK
        (snapshot_ids[3], 4, "pre_execution", "blocked"),    # task 4 BLOCK
        (snapshot_ids[4], 5, "pre_execution", "allowed"),    # task 5 ALLOW
        (snapshot_ids[4], 5, "post_execution", "completed"), # task 5 completed
        (snapshot_ids[5], 6, "pre_execution", "blocked"),    # task 6 BLOCK
    ]
    for sid, tid, btype, outcome in bindings:
        ccm.bind_execution(sid, tid, btype, outcome)

    return ccm


class _MockConstraintSet:
    """Minimal mock for ConstraintSet used in GateResult."""
    def __init__(self, blocks=None, holds=None, allows=None, verdict="ALLOW", reason=""):
        self._blocks = blocks or []
        self._holds = holds or []
        self._allows = allows or []
        self.verdict = verdict
        self.reason = reason
        self.satisfiable = verdict != "BLOCK"

    def to_dict(self, max_per_type=50):
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "satisfiable": self.satisfiable,
            "blocks": self._blocks,
            "holds": self._holds,
            "allows": self._allows,
        }


class _MockGateResult:
    """Minimal mock for GateResult."""
    def __init__(self, constraints=None, verdict="ALLOW", reason="", context_snapshot=None):
        self.constraints = constraints
        self.verdict = verdict
        self.reason = reason
        self.satisfiable = verdict != "BLOCK"
        self.context_snapshot = context_snapshot or {}


class TestConstraintQueryEngine(unittest.TestCase):
    """Full CQE verification: Query → Aggregation → Projection"""

    @classmethod
    def setUpClass(cls):
        cls.db = tempfile.mktemp(suffix="_v85c_test.db")
        conn = sqlite3.connect(cls.db)
        init_v85b_tables(conn)
        conn.close()
        _seed_data(cls.db)
        cls.cqe = ConstraintQueryEngine(cls.db)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.db)
        except PermissionError:
            pass

    # ── Query Layer ───────────────────────────────────────────────

    def test_query_verdict_filter(self):
        """query(verdict='BLOCK') returns only BLOCK snapshots"""
        results = self.cqe.query(verdict="BLOCK")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["verdict"], "BLOCK")

    def test_query_task_type_filter(self):
        """query(task_type='modify_order') returns only modify_order snapshots"""
        results = self.cqe.query(task_type="modify_order")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["task_type"], "modify_order")

    def test_query_customer_filter(self):
        """query(customer_id='C001') returns only C001 snapshots"""
        results = self.cqe.query(customer_id="C001")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["customer_id"], "C001")

    def test_query_combined_filter(self):
        """query(verdict='BLOCK', task_type='cancel_order')"""
        results = self.cqe.query(verdict="BLOCK", task_type="cancel_order")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["verdict"], "BLOCK")
            self.assertEqual(r["task_type"], "cancel_order")

    def test_query_since_days(self):
        """query(since_days=2) returns only recent snapshots"""
        results = self.cqe.query(since_days=2)
        self.assertGreater(len(results), 0)
        now = time.time()
        for r in results:
            self.assertGreaterEqual(r["created_at"], now - 2 * 86400 - 10)  # 10s tolerance

    def test_query_execution_outcome(self):
        """query(execution_outcome='blocked') joins bindings"""
        results = self.cqe.query(execution_outcome="blocked")
        self.assertGreater(len(results), 0)

    def test_query_blocks_contains(self):
        """query(blocks_contains={'policy_id': 'BIZ_CANCEL_001'})"""
        results = self.cqe.query(blocks_contains={"policy_id": "BIZ_CANCEL_001"})
        self.assertGreater(len(results), 0)
        for r in results:
            pids = [b["policy_id"] for b in r.get("blocks", [])]
            self.assertIn("BIZ_CANCEL_001", pids)

    def test_query_context_field(self):
        """query(context__order_status='in_production') via json_extract"""
        results = self.cqe.query(context__order_status="in_production")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r.get("context_snapshot", {}).get("order_status"), "in_production")

    def test_query_context_comparison(self):
        """query(context__customer_risk__gt=0.4) —  GT comparison on JSON field"""
        results = self.cqe.query(context__customer_risk__gt=0.4)
        self.assertGreater(len(results), 0)
        for r in results:
            risk = r.get("context_snapshot", {}).get("customer_risk", 0)
            self.assertGreater(risk, 0.4)

    def test_query_empty_result(self):
        """query with no match returns empty list"""
        results = self.cqe.query(verdict="NONEXISTENT")
        self.assertEqual(results, [])

    # ── Aggregation Layer — Policy Impact ─────────────────────────

    def test_policy_impact_biz_cancel(self):
        """policy_impact('BIZ_CANCEL_001') returns correct counts"""
        result = self.cqe.policy_impact("BIZ_CANCEL_001", days=30)
        self.assertGreater(result["trigger_count"], 0)
        self.assertGreater(result["block_count"], 0)
        self.assertIn("block_rate", result)
        self.assertIn("estimate", result)

    def test_policy_impact_nonexistent(self):
        """policy_impact of unknown policy returns zero counts"""
        result = self.cqe.policy_impact("NONEXISTENT_POLICY", days=30)
        self.assertEqual(result["trigger_count"], 0)
        self.assertEqual(result["block_count"], 0)

    # ── Aggregation Layer — Context Patterns ──────────────────────

    def test_context_patterns(self):
        """context_patterns() returns grouped context patterns sorted by count"""
        results = self.cqe.context_patterns(days=30)
        self.assertGreater(len(results), 0)
        # Verify sorted descending
        counts = [r["count"] for r in results]
        self.assertEqual(counts, sorted(counts, reverse=True))
        # Each result has verdict_distribution
        for r in results:
            self.assertIn("verdict_distribution", r)
            self.assertIn("count", r)

    def test_context_patterns_filtered(self):
        """context_patterns(verdict='BLOCK') filters to BLOCK snapshots"""
        results = self.cqe.context_patterns(verdict="BLOCK", days=30)
        self.assertGreater(len(results), 0)
        # Each group should have BLOCK verdicts
        for r in results:
            total_block = r["verdict_distribution"].get("BLOCK", 0)
            total_other = sum(v for k, v in r["verdict_distribution"].items() if k != "BLOCK")
            self.assertGreater(total_block, 0)

    # ── Aggregation Layer — Customer Profile ──────────────────────

    def test_customer_profile(self):
        """customer_profile('C001') returns customer constraint profile"""
        profile = self.cqe.customer_profile("C001")
        self.assertEqual(profile["customer_id"], "C001")
        self.assertGreater(profile["total_evaluations"], 0)
        self.assertIn("by_verdict", profile)
        self.assertIn("by_task_type", profile)
        self.assertIn("top_blocking_policies", profile)

    def test_customer_profile_blocking_policies(self):
        """customer_profile shows top blocking policies"""
        profile = self.cqe.customer_profile("C001")
        if profile["top_blocking_policies"]:
            top = profile["top_blocking_policies"][0]
            self.assertIn("policy_id", top)
            self.assertIn("count", top)

    # ── Projection Layer ──────────────────────────────────────────

    def test_project_by_policy(self):
        """project(filter={'verdict': 'BLOCK'}, group_by='policy_id')"""
        results = self.cqe.project(
            filter={"verdict": "BLOCK"},
            group_by="policy_id",
            metric="sum(order_value)",
            days=30,
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("policy_id", r)
            self.assertIn("count", r)
            self.assertIn("total_revenue_affected", r)

    def test_project_by_verdict(self):
        """project(group_by='verdict') groups by direct column"""
        results = self.cqe.project(
            filter={},
            group_by="verdict",
            metric="sum(order_value)",
            days=30,
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("verdict", r)
            self.assertIn("count", r)

    def test_project_with_context_filter(self):
        """project(filter with context__customer_risk__gt) — JSON filter + group_by"""
        results = self.cqe.project(
            filter={"verdict": "BLOCK", "context__customer_risk__gt": 0.2},
            group_by="policy_id",
            metric="sum(order_value)",
            days=30,
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("policy_id", r)

    # ── Edge Cases ────────────────────────────────────────────────

    def test_query_limit_offset(self):
        """query(limit=1, offset=0) returns at most 1 result"""
        results = self.cqe.query(limit=1, order="asc")
        self.assertLessEqual(len(results), 1)

    def test_query_sort_order(self):
        """query(sort='created_at', order='asc') sorts ascending"""
        results = self.cqe.query(sort="created_at", order="asc", limit=5)
        timestamps = [r["created_at"] for r in results]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_empty_db(self):
        """CQE on empty DB returns empty results without error"""
        empty_db = tempfile.mktemp(suffix="_empty_test.db")
        conn = sqlite3.connect(empty_db)
        init_v85b_tables(conn)
        conn.close()
        cqe = ConstraintQueryEngine(empty_db)
        self.assertEqual(cqe.query(verdict="BLOCK"), [])
        self.assertEqual(cqe.policy_impact("TEST", days=7)["trigger_count"], 0)
        self.assertEqual(cqe.context_patterns(days=7), [])
        self.assertEqual(cqe.customer_profile("NONEXISTENT")["total_evaluations"], 0)
        self.assertEqual(cqe.project(filter={}, group_by="policy_id", days=7), [])
        try:
            os.unlink(empty_db)
        except PermissionError:
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
