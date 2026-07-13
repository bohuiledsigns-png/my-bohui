"""V8.5-C2: Daily Verification — full chain orchestration.

Runs the complete verification pipeline:
  export (production DB) → replay × 3 → pairwise diff → metrics → summary

Usage:
    python scripts/verify_all.py
    python scripts/verify_all.py --db crm_data.db
    python scripts/verify_all.py --fixture tasks.json   # skip export, use existing
    python scripts/verify_all.py --output-dir ./verify_reports

Output:
    ./verify_reports/<timestamp>/  — all run dumps + report.json
    Exit code: 0 if PASS, 1 if FAIL

    Reports older than 30 days are auto-cleaned on each run.
    Use --history to list recent report summaries.

Designed for unattended daily cron execution.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("verify_all")


def _timestamp_dir(base: str) -> str:
    """Create a timestamped output directory."""
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = os.path.join(base, ts)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _cleanup_old_reports(base: str, max_days: int = 30):
    """Remove report directories older than max_days."""
    if not os.path.isdir(base):
        return
    now = datetime.now()
    cutoff = now - timedelta(days=max_days)
    for entry in os.listdir(base):
        entry_path = os.path.join(base, entry)
        if not os.path.isdir(entry_path):
            continue
        # Parse timestamp prefix: YYYY-MM-DD_HHMMSS
        try:
            ts = datetime.strptime(entry[:17], "%Y-%m-%d_%H%M%S")
            if ts < cutoff:
                import shutil
                shutil.rmtree(entry_path, ignore_errors=True)
                logger.info("Cleaned old report: %s", entry)
        except (ValueError, IndexError):
            continue  # skip non-timestamp directories


def print_history(base: str, limit: int = 7):
    """Print a compact history of recent verification reports."""
    if not os.path.isdir(base):
        print("No reports directory found:", base)
        return

    entries = []
    for entry in os.listdir(base):
        report_path = os.path.join(base, entry, "report.json")
        if not os.path.isfile(report_path):
            continue
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            status = report.get("overall_status", "?")
            elapsed = report.get("elapsed_seconds", 0)
            task_count = 0
            if report.get("steps", {}).get("export", {}).get("status") == "PASS":
                task_count = report["steps"]["export"].get("task_count", 0)
            elif report.get("steps", {}).get("export", {}).get("status") == "SKIPPED":
                task_count = report["steps"]["export"].get("task_count", 0)

            entries.append((entry, status, task_count, elapsed))
        except (json.JSONDecodeError, KeyError):
            continue

    entries.sort(reverse=True)  # newest first
    if not entries:
        print("No reports found.")
        return

    print()
    print(f"  Recent reports ({len(entries)} total, showing {min(limit, len(entries))}):")
    print(f"  {'Date':<20} {'Status':<8} {'Tasks':<8} {'Time':<8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8}")
    for entry, status, task_count, elapsed in entries[:limit]:
        print(f"  {entry:<20} {status:<8} {task_count:<8} {elapsed:<8.1f}s")
    print()


def run_pipeline(db_path: str = None, fixture_path: str = None,
                 output_dir: str = "./verify_reports", runs: int = 3) -> dict:
    """Run the full verification pipeline and return a summary report.

    Args:
        db_path: Path to production DB (for export). None if using fixture.
        fixture_path: Path to existing fixture. None if using export.
        output_dir: Base output directory (timestamped subdir created).
        runs: Number of replay runs (default 3).

    Returns:
        dict with overall_status, metrics, and paths to all artifacts.
    """
    # Create timestamped output directory
    out_dir = _timestamp_dir(output_dir)
    logger.info("Output directory: %s", out_dir)

    pipeline = {
        "pipeline_started_at": time.time(),
        "output_dir": out_dir,
        "steps": {},
        "overall_status": "UNKNOWN",
    }

    # ── Step 1: Export (or use provided fixture) ──────────────────────
    if fixture_path:
        logger.info("Using existing fixture: %s", fixture_path)
        fixture = json.load(open(fixture_path, "r", encoding="utf-8"))
        pipeline["steps"]["export"] = {
            "status": "SKIPPED",
            "source": fixture_path,
            "task_count": len(fixture.get("tasks", [])),
            "note": "fixture provided, export skipped",
        }
    elif db_path:
        logger.info("Exporting tasks from: %s", db_path)
        if not os.path.exists(db_path):
            error_msg = f"Database not found: {db_path}"
            logger.error(error_msg)
            pipeline["steps"]["export"] = {"status": "FAIL", "error": error_msg}
            pipeline["overall_status"] = "FAIL"
            return pipeline

        from scripts.verify_replay import export_tasks
        try:
            fixture_path = os.path.join(out_dir, "exported_tasks.json")
            fixture = export_tasks(db_path, fixture_path)
            pipeline["steps"]["export"] = {
                "status": "PASS",
                "source": db_path,
                "fixture_path": fixture_path,
                "task_count": fixture["meta"]["task_count"],
            }
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            pipeline["steps"]["export"] = {"status": "FAIL", "error": str(exc)}
            pipeline["overall_status"] = "FAIL"
            return pipeline
    else:
        error_msg = "Either --db or --fixture is required"
        pipeline["steps"]["export"] = {"status": "FAIL", "error": error_msg}
        pipeline["overall_status"] = "FAIL"
        return pipeline

    # Check for empty fixture
    task_count = len(fixture.get("tasks", []))
    if task_count == 0:
        logger.warning("No tasks to replay — skipping replay phase")
        pipeline["steps"]["replay"] = {"status": "SKIPPED", "reason": "no tasks"}
        pipeline["steps"]["diff"] = {"status": "SKIPPED", "reason": "no replay data"}
        pipeline["steps"]["metrics"] = {"status": "SKIPPED", "reason": "no replay data"}
        pipeline["overall_status"] = "PASS"
        return pipeline

    # ── Step 2: Replay × N ───────────────────────────────────────────
    from scripts.verify_replay import run_replay

    run_dumps = []
    run_paths = []
    replay_ok = True
    for i in range(1, runs + 1):
        try:
            logger.info("[Replay] Run %d/%d", i, runs)
            state = run_replay(fixture, out_dir, i)
            run_dumps.append(state)
            run_path = os.path.join(out_dir, f"run_{i}.json")
            run_paths.append(run_path)
            qs = state.get("queue_summary", {})
            processed = state["meta"]["tasks_processed"]
            logger.info("[Replay] Run %d: %d processed, queue=%s", i, processed, qs)
        except Exception as exc:
            logger.error("[Replay] Run %d failed: %s", i, exc)
            pipeline["steps"]["replay"] = {
                "status": "FAIL",
                "error": str(exc),
                "run": i,
            }
            replay_ok = False
            break

    if not replay_ok:
        pipeline["overall_status"] = "FAIL"
        return pipeline

    pipeline["steps"]["replay"] = {
        "status": "PASS",
        "runs": runs,
        "run_paths": run_paths,
        "drain_results": [
            {
                "run": i + 1,
                "processed": d["meta"]["tasks_processed"],
                "queue_summary": d.get("queue_summary", {}),
                "snapshots": len(d.get("constraint_snapshots", [])),
                "bindings": len(d.get("constraint_execution_bindings", [])),
            }
            for i, d in enumerate(run_dumps)
        ],
    }

    # ── Step 3: Pairwise Diff ────────────────────────────────────────
    from scripts.verify_metrics import compute_divergence_rate

    labels = [f"run_{i}" for i in range(1, runs + 1)]
    try:
        div_result = compute_divergence_rate(run_dumps, labels)
        pipeline["steps"]["diff"] = {
            "status": "PASS" if div_result["max_divergence_rate"] == 0.0 else "FAIL",
            "max_divergence_rate": div_result["max_divergence_rate"],
            "num_comparisons": div_result["num_comparisons"],
            "pairwise": [
                {
                    "pair": p["pair"],
                    "status": p["status"],
                    "divergence_rate": p["divergence_rate"],
                    "divergent": p["divergent"],
                    "total_checks": p["total_checks"],
                }
                for p in div_result["pairwise"]
            ],
        }
    except Exception as exc:
        logger.error("Diff check failed: %s", exc)
        pipeline["steps"]["diff"] = {"status": "FAIL", "error": str(exc)}
        pipeline["overall_status"] = "FAIL"
        return pipeline

    # ── Step 4: Metrics ──────────────────────────────────────────────
    from scripts.verify_metrics import (
        compute_duplicate_rate,
        compute_policy_instability,
        TARGETS,
    )

    try:
        dup = compute_duplicate_rate(run_dumps[0])
        inst = compute_policy_instability(run_dumps)

        metrics = {
            "duplicate_execution_rate": {
                "value": dup["rate"],
                "target": TARGETS["duplicate_execution_rate"]["label"],
                "pass": dup["rate"] <= TARGETS["duplicate_execution_rate"]["max"],
                "details": {
                    "total_tasks": dup["total_tasks"],
                    "duplicates": dup["duplicates"],
                    "unique_keys_with_duplicates": dup["unique_keys_with_duplicates"],
                },
            },
            "state_divergence_rate": {
                "value": div_result["max_divergence_rate"],
                "target": TARGETS["state_divergence_rate"]["label"],
                "pass": div_result["max_divergence_rate"] <= TARGETS["state_divergence_rate"]["max"],
                "details": {
                    "num_comparisons": div_result["num_comparisons"],
                },
            },
            "policy_instability": {
                "value": inst["instability_rate"],
                "target": TARGETS["policy_instability"]["label"],
                "pass": inst["instability_rate"] <= TARGETS["policy_instability"]["max"],
                "details": {
                    "total_evaluations": inst["total_evaluations"],
                    "unstable_task_count": inst["unstable_task_count"],
                },
            },
        }

        all_pass = all(m["pass"] for m in metrics.values())
        pipeline["steps"]["metrics"] = {
            "status": "PASS" if all_pass else "FAIL",
            "metrics": metrics,
        }
        pipeline["overall_status"] = "PASS" if all_pass else "FAIL"

    except Exception as exc:
        logger.error("Metrics computation failed: %s", exc)
        pipeline["steps"]["metrics"] = {"status": "FAIL", "error": str(exc)}
        pipeline["overall_status"] = "FAIL"
        return pipeline

    # ── Write report ─────────────────────────────────────────────────
    pipeline["pipeline_finished_at"] = time.time()
    pipeline["elapsed_seconds"] = round(
        pipeline["pipeline_finished_at"] - pipeline["pipeline_started_at"], 2
    )

    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(pipeline, f, ensure_ascii=False, indent=2, default=str)
    logger.info("Report written: %s", report_path)

    # Clean up reports older than 30 days
    try:
        _cleanup_old_reports(output_dir, max_days=30)
    except Exception as exc:
        logger.warning("Report cleanup failed (non-fatal): %s", exc)

    return pipeline


def print_summary(pipeline: dict):
    """Print a human-readable summary of the pipeline results."""
    status = pipeline["overall_status"]
    print()
    print("=" * 60)
    print(f"  V8.5-C2 Daily Verification  [{status}]")
    print("=" * 60)
    print(f"  Output:    {pipeline.get('output_dir', '?')}")
    elapsed = pipeline.get("elapsed_seconds", 0)
    print(f"  Elapsed:   {elapsed:.1f}s")
    print()

    # Step 1: Export
    export = pipeline["steps"].get("export", {})
    print(f"  1. Export           [{export.get('status', '?')}]")
    if export.get("status") == "PASS":
        print(f"     Tasks exported:  {export.get('task_count', 0)}")
    elif export.get("status") == "SKIPPED":
        print(f"     {export.get('note', 'skipped')}")
    elif export.get("error"):
        print(f"     ERROR: {export.get('error')}")
    print()

    # Step 2: Replay
    replay = pipeline["steps"].get("replay", {})
    print(f"  2. Replay x{replay.get('runs', '?')}         [{replay.get('status', '?')}]")
    if replay.get("status") == "PASS":
        for r in replay.get("drain_results", []):
            qs = r["queue_summary"]
            qs_str = ", ".join(f"{k}={v}" for k, v in sorted(qs.items()))
            print(f"     Run {r['run']}: {r['processed']} processed  ({qs_str})"
                  f"  snapshots={r['snapshots']}  bindings={r['bindings']}")
    elif replay.get("status") == "SKIPPED":
        print(f"     {replay.get('reason', '')}")
    elif replay.get("error"):
        print(f"     ERROR at run {replay.get('run', '?')}: {replay.get('error')}")
    print()

    # Step 3: Diff
    diff = pipeline["steps"].get("diff", {})
    print(f"  3. Pairwise Diff    [{diff.get('status', '?')}]")
    if diff.get("status") == "PASS":
        for p in diff.get("pairwise", []):
            print(f"     {p['pair']}: {p['divergent']}/{p['total_checks']} divergent  "
                  f"(rate={p['divergence_rate']})")
    elif diff.get("status") == "SKIPPED":
        print(f"     {diff.get('reason', '')}")
    elif diff.get("error"):
        print(f"     ERROR: {diff.get('error')}")
    print()

    # Step 4: Metrics
    metrics_step = pipeline["steps"].get("metrics", {})
    print(f"  4. Metrics          [{metrics_step.get('status', '?')}]")
    if metrics_step.get("status") in ("PASS", "FAIL"):
        for name, m in metrics_step.get("metrics", {}).items():
            icon = "PASS" if m["pass"] else "FAIL"
            print(f"     {name}: {m['value']} (target: {m['target']}) [{icon}]")
    elif metrics_step.get("error"):
        print(f"     ERROR: {metrics_step.get('error')}")

    print()
    print(f"  Overall: {status}")
    print("=" * 60)


def print_trend(base: str, limit: int = 30):
    """Print a table of metrics over recent runs."""
    if not os.path.isdir(base):
        print("No reports directory found:", base)
        return

    entries = []
    for entry in os.listdir(base):
        report_path = os.path.join(base, entry, "report.json")
        if not os.path.isfile(report_path):
            continue
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            status = report.get("overall_status", "?")
            elapsed = report.get("elapsed_seconds", 0)
            task_count = 0
            if report.get("steps", {}).get("export", {}).get("status") == "PASS":
                task_count = report["steps"]["export"].get("task_count", 0)

            metrics = report.get("steps", {}).get("metrics", {}).get("metrics", {})
            dup = metrics.get("duplicate_execution_rate", {}).get("value", "?")
            div = metrics.get("state_divergence_rate", {}).get("value", "?")
            inst = metrics.get("policy_instability", {}).get("value", "?")

            entries.append((entry[:10], entry, status, task_count, dup, div, inst, elapsed))
        except (json.JSONDecodeError, KeyError):
            continue

    entries.sort(reverse=True)  # newest first
    entries = entries[:limit]

    if not entries:
        print("No reports found.")
        return

    print()
    print(f"  Metrics Trend (last {len(entries)} runs)")
    print(f"  {'Date':<12} {'Status':<8} {'Tasks':<7} {'Dup':<8} {'Diverg':<8} {'Instab':<8} {'Time':<8}")
    print(f"  {'-'*12} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for date_label, entry, status, task_count, dup, div, inst, elapsed in entries:
        print(f"  {date_label:<12} {status:<8} {task_count:<7} {dup:<8} {div:<8} {inst:<8} {elapsed:<8.1f}s")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="V8.5-C2 Daily Verification — full chain orchestration",
    )
    parser.add_argument("--history", action="store_true",
                        help="Show recent report summaries and exit")
    parser.add_argument("--trend", action="store_true",
                        help="Show metrics trend table over time and exit")
    parser.add_argument("--db", default=None,
                        help="Production database path")
    parser.add_argument("--fixture", default=None,
                        help="Existing fixture path (skip export)")
    parser.add_argument("--output-dir", default="./verify_reports",
                        help="Base output directory (default: ./verify_reports)")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of replay runs (default: 3)")
    args = parser.parse_args()

    if args.history:
        print_history(args.output_dir)
        sys.exit(0)

    if args.trend:
        print_trend(args.output_dir)
        sys.exit(0)

    # Default: look for production DB in project root
    if not args.fixture and not args.db:
        candidate = os.path.join(PROJECT_ROOT, "crm_data.db")
        if os.path.exists(candidate):
            args.db = candidate
        else:
            print("No production DB found at default path.")
            print("Usage: python scripts/verify_all.py --db <path>  or  --fixture <path>")
            sys.exit(1)

    pipeline = run_pipeline(
        db_path=args.db,
        fixture_path=args.fixture,
        output_dir=args.output_dir,
        runs=args.runs,
    )

    print_summary(pipeline)
    sys.exit(0 if pipeline["overall_status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
