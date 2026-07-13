"""V8.5-C2: Replay Runner — deterministic execution kernel replayer.

Two modes:
  export   — extract execution_queue tasks from production DB to JSON fixture
  replay   — create sandbox DB, replay fixture tasks × N, dump execution state

Usage:
    python scripts/verify_replay.py export --db crm_data.db --output tasks.json
    python scripts/verify_replay.py replay --input tasks.json --runs 3 --output-dir ./replay_output

Constraints:
  - READ-ONLY on production DB (export mode)
  - No modification to execution/, safety/, app.py
  - External tool, manually run, no daemon
"""

import argparse
import json
import logging
import os
import sys
import sqlite3
import tempfile
import time
import traceback

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("verify_replay")

# ── Generic handlers (non-invasive, no external dependencies) ──────────


def _handler_generic_ok(payload):
    """Generic handler that always succeeds without side effects.

    This is the key to non-invasive replay: handlers that don't call
    WhatsApp, don't call external APIs, just return success.
    The execution pipeline (gate, queue, traces, snapshots) is exercised
    fully without any business logic dependency.
    """
    return {"ok": True, "simulated": True}


def _handler_simulate_update_crm(payload):
    """Simulate update_crm without needing the real CRM state."""
    return {"ok": True, "simulated_update": True}


REPLAY_HANDLERS = {
    "send_message": _handler_generic_ok,
    "update_crm": _handler_simulate_update_crm,
}


# ── Sandbox DB helpers ──────────────────────────────────────────────


def _create_sandbox_db(sandbox_path: str) -> None:
    """Create a full sandbox database by monkey-patching database.DB_PATH.

    This is the only way to get a complete, production-identical schema
    without modifying database.py or app.py.
    """
    import database as db_mod

    original_path = db_mod.DB_PATH
    db_mod.DB_PATH = sandbox_path
    try:
        db_mod.init_db()
        logger.info("Sandbox DB created: %s", sandbox_path)
    finally:
        db_mod.DB_PATH = original_path


def _get_conn(db_path: str) -> sqlite3.Connection:
    """Open a standard connection to any DB path."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Export mode ────────────────────────────────────────────────────


def export_tasks(db_path: str, output_path: str, limit: int = 200) -> dict:
    """Extract execution_queue tasks from a (production) database.

    Returns a JSON-serialisable fixture with:
      - tasks: list of {task_type, payload, execution_key, priority, created_at}
      - meta: export timestamp, source path, count

    This is READ-ONLY. No INSERT/UPDATE/DELETE.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            """SELECT id, task_type, payload_json, execution_key, priority,
                      status, retry_count, created_at
               FROM execution_queue
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        tasks = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}

            tasks.append({
                "id": r["id"],
                "task_type": r["task_type"],
                "payload": payload,
                "execution_key": r["execution_key"] or "",
                "priority": r["priority"],
                "original_status": r["status"],
                "original_retry_count": r["retry_count"],
                "created_at": r["created_at"],
            })

        fixture = {
            "meta": {
                "exported_at": time.time(),
                "source_db": db_path,
                "task_count": len(tasks),
                "format_version": "1.0",
            },
            "tasks": tasks,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(fixture, f, ensure_ascii=False, indent=2)

        logger.info(
            "Exported %d tasks to %s",
            len(tasks), output_path,
        )
        return fixture
    finally:
        conn.close()


# ── Replay mode ─────────────────────────────────────────────────────


def _insert_tasks_direct(conn, tasks: list) -> None:
    """Insert fixture tasks directly into execution_queue (bypass enqueue).

    Each task is inserted with 'pending' status and its original execution_key,
    so the WorkerLoop's idempotency check and gate evaluation run on the
    same inputs as production.
    """
    now = time.time()
    for task in tasks:
        try:
            conn.execute(
                """INSERT INTO execution_queue
                   (task_type, payload_json, execution_key, priority, status,
                    retry_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
                (
                    task["task_type"],
                    json.dumps(task["payload"], ensure_ascii=False),
                    task.get("execution_key", ""),
                    task.get("priority", 5),
                    task.get("created_at", now),
                    now,
                ),
            )
        except Exception as exc:
            logger.warning(
                "[Replay] Skipping task %s (type=%s): %s",
                task.get("id"), task.get("task_type"), exc,
            )
    conn.commit()


def _dump_sandbox_state(db_path: str) -> dict:
    """Extract full execution state from a sandbox DB as a JSON-safe dict."""
    state = {}
    conn = _get_conn(db_path)
    try:
        # 1. execution_queue
        rows = conn.execute(
            """SELECT id, task_type, status, retry_count, execution_key,
                      error, result_json, trace_log, priority, locked_by,
                      created_at, updated_at
               FROM execution_queue ORDER BY id"""
        ).fetchall()
        state["execution_queue"] = []
        for r in rows:
            row = dict(r)
            # Parse JSON fields for cleaner diff
            for jf in ("result_json", "trace_log"):
                try:
                    row[jf] = json.loads(row[jf]) if row[jf] else None
                except (json.JSONDecodeError, TypeError):
                    pass
            state["execution_queue"].append(row)

        # 2. constraint_snapshots
        try:
            rows = conn.execute(
                """SELECT id, task_id, customer_id, task_type, verdict, reason,
                          satisfiable, blocks_json, holds_json, allows_json,
                          policy_count, context_snapshot_json, created_at
                   FROM constraint_snapshots ORDER BY id"""
            ).fetchall()
            state["constraint_snapshots"] = [dict(r) for r in rows]
        except Exception:
            state["constraint_snapshots"] = []

        # 3. constraint_execution_bindings
        try:
            rows = conn.execute(
                """SELECT id, snapshot_id, task_id, binding_type,
                          execution_outcome, created_at
                   FROM constraint_execution_bindings ORDER BY id"""
            ).fetchall()
            state["constraint_execution_bindings"] = [dict(r) for r in rows]
        except Exception:
            state["constraint_execution_bindings"] = []

        # 4. execution_dlq
        try:
            rows = conn.execute(
                """SELECT id, original_id, execution_key, task_type, error,
                          retry_count, moved_at
                   FROM execution_dlq ORDER BY id"""
            ).fetchall()
            state["execution_dlq"] = [dict(r) for r in rows]
        except Exception:
            state["execution_dlq"] = []

        # 5. execution_queue status summary
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM execution_queue GROUP BY status"
        ).fetchall()
        state["queue_summary"] = {r["status"]: r["cnt"] for r in rows}

    finally:
        conn.close()

    return state


def run_replay(tasks_fixture: dict, output_dir: str, run_num: int) -> dict:
    """Execute a single replay run in a sandbox DB.

    Steps:
      1. Create sandbox DB with full schema
      2. Instantiate sandbox ExecutionQueue + WorkerLoop
      3. Register generic handlers (no external dependencies)
      4. Insert fixture tasks
      5. Process all tasks via WorkerLoop
      6. Dump and return execution state
    """
    sandbox_path = os.path.join(output_dir, f"sandbox_{run_num}.db")

    # ── Patch database.DB_PATH for the ENTIRE replay scope ──
    # Critical: BusinessPolicyGate._get_ccm() and other internal
    # components read database.DB_PATH at lazy-init time. We must
    # keep it pointing at the sandbox until the WorkerLoop finishes.
    import database as _db_mod
    _orig_db_path = _db_mod.DB_PATH
    _db_mod.DB_PATH = sandbox_path
    try:
        # Step 1: Create sandbox DB
        _create_sandbox_db(sandbox_path)

        # Step 2: Instantiate sandbox components
        from execution.execution_queue import ExecutionQueue
        from execution.kernel import IdempotencyGuard, DeadLetterQueue, WorkerLoop

        queue = ExecutionQueue(db_path=sandbox_path)
        worker = WorkerLoop(queue, interval=0.5)
        worker._guard = IdempotencyGuard(db_path=sandbox_path)
        worker._dlq = DeadLetterQueue(db_path=sandbox_path)

        # Step 3: Build and register handlers for ALL task types in fixture
        # Collect unique task types from the fixture and ensure every type
        # has a handler. Unknown types get the generic ok handler so the
        # full gate pipeline runs instead of early-exiting at "no handler".
        task_types_in_fixture = set(
            t.get("task_type", "") for t in tasks_fixture.get("tasks", [])
        )
        handler_map = dict(REPLAY_HANDLERS)
        for ttype in task_types_in_fixture:
            if ttype and ttype not in handler_map:
                handler_map[ttype] = _handler_generic_ok
                logger.debug("[Replay] Auto-registered fallback handler for '%s'", ttype)
        worker.register_handlers(handler_map)

        # Step 4: Insert tasks directly (bypass enqueue to preserve execution_keys)
        insert_conn = _get_conn(sandbox_path)
        try:
            _insert_tasks_direct(insert_conn, tasks_fixture["tasks"])
        finally:
            insert_conn.close()

        # Step 5: Process tasks — single-threaded drain loop
        processed = 0
        max_iterations = 50  # safety limit
        for iteration in range(max_iterations):
            tasks = queue.dequeue("verify_replay", batch_size=5)
            if not tasks:
                break
            for task in tasks:
                try:
                    worker._process_task(task)
                except Exception as exc:
                    logger.warning(
                        "[Replay] Task %s (%s) raised: %s",
                        task["id"], task["task_type"], exc,
                    )
                processed += 1

        logger.info(
            "[Replay] Run %d processed %d tasks (%d iterations)",
            run_num, processed, iteration + 1,
        )

        # Step 6: Dump state
        state = _dump_sandbox_state(sandbox_path)
        state["meta"] = {
            "run_number": run_num,
            "tasks_input": len(tasks_fixture["tasks"]),
            "tasks_processed": processed,
            "replayed_at": time.time(),
        }

        dump_path = os.path.join(output_dir, f"run_{run_num}.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)

        logger.info("[Replay] Run %d state dumped to %s", run_num, dump_path)
        return state

    finally:
        # Always restore DB_PATH to the original, even on error
        _db_mod.DB_PATH = _orig_db_path
        # Clean up sandbox DB files
        try:
            os.unlink(sandbox_path)
            for ext in ("-wal", "-shm"):
                p = sandbox_path + ext
                if os.path.exists(p):
                    os.unlink(p)
        except PermissionError:
            pass


# ── CLI ──────────────────────────────────────────────────────────────


def cmd_export(args):
    """CLI handler for 'export' subcommand."""
    fixture = export_tasks(args.db, args.output, limit=args.limit)
    print(f"Exported {fixture['meta']['task_count']} tasks to {args.output}")


def cmd_replay(args):
    """CLI handler for 'replay' subcommand."""
    with open(args.input, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    runs = args.runs
    states = []
    for i in range(1, runs + 1):
        logger.info("[Replay] Starting run %d/%d", i, runs)
        state = run_replay(fixture, args.output_dir, i)
        states.append(state)

    # Print summary
    for i, s in enumerate(states, 1):
        qs = s.get("queue_summary", {})
        snap_count = len(s.get("constraint_snapshots", []))
        bind_count = len(s.get("constraint_execution_bindings", []))
        processed = s["meta"]["tasks_processed"]
        print(
            f"Run {i}: {processed} processed, "
            f"queue={qs}, snapshots={snap_count}, bindings={bind_count}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="V8.5-C2 Replay Runner — deterministic execution verifier",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # export
    exp = sub.add_parser("export", help="Export tasks from production DB")
    exp.add_argument("--db", default="crm_data.db",
                     help="Path to production database (default: crm_data.db)")
    exp.add_argument("--output", default="tasks.json",
                     help="Output JSON fixture path")
    exp.add_argument("--limit", type=int, default=200,
                     help="Max tasks to export (default: 200)")
    exp.set_defaults(func=cmd_export)

    # replay
    rep = sub.add_parser("replay", help="Replay tasks in sandbox")
    rep.add_argument("--input", default="tasks.json",
                     help="Input JSON fixture path")
    rep.add_argument("--runs", type=int, default=3,
                     help="Number of replay runs (default: 3)")
    rep.add_argument("--output-dir", default="./replay_output",
                     help="Output directory for run dumps")
    rep.set_defaults(func=cmd_replay)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
