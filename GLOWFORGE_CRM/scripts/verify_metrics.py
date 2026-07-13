"""V8.5-C2: Metrics Monitor — compute 3 stability metrics from replay dumps.

Reads replay dump JSON files and computes the three key stability indicators:
  1. Duplicate Execution Rate
  2. State Divergence Rate (from diff report)
  3. Policy Instability

Usage:
    python scripts/verify_metrics.py run_1.json run_2.json
    python scripts/verify_metrics.py run_1.json run_2.json run_3.json

Output:
    JSON report with all three metrics + pass/fail per metric.
"""

import json
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("verify_metrics")

# Target thresholds
TARGETS = {
    "duplicate_execution_rate": {"max": 0.0, "label": "0"},
    "state_divergence_rate": {"max": 0.0, "label": "0"},
    "policy_instability": {"max": 0.01, "label": "< 1%"},
}


def load_dump(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Metric 1: Duplicate Execution Rate ──────────────────────────────


def compute_duplicate_rate(dump: dict) -> dict:
    """Count duplicate executions from a single replay dump.

    A "duplicate" is when the same execution_key appears more than once
    with status='completed' in the execution_queue.

    Returns:
        {"rate": float, "total_tasks": int, "duplicates": int, "duplicate_keys": [str]}
    """
    queue = dump.get("execution_queue", [])
    total = len(queue)

    # Group by execution_key
    key_counts = {}
    for task in queue:
        ek = task.get("execution_key", "") or ""
        if ek:
            key_counts.setdefault(ek, {"count": 0, "completed": 0})
            key_counts[ek]["count"] += 1
            if task.get("status") == "completed":
                key_counts[ek]["completed"] += 1

    duplicates = 0
    dup_keys = []
    for ek, info in key_counts.items():
        if info["completed"] > 1:
            duplicates += info["completed"] - 1
            dup_keys.append(ek)

    rate = round(duplicates / total, 4) if total > 0 else 0.0
    return {
        "rate": rate,
        "total_tasks": total,
        "duplicates": duplicates,
        "unique_keys_with_duplicates": len(dup_keys),
        "duplicate_keys": dup_keys[:20],  # cap output
    }


# ── Metric 2: State Divergence Rate ─────────────────────────────────


def compute_divergence_rate(dumps: list, labels: list) -> dict:
    """Compute divergence rate across multiple replay dumps.

    Uses pairwise comparison: A vs B, A vs C, B vs C.
    Returns the maximum divergence rate observed.

    Args:
        dumps: List of replay dump dicts
        labels: Corresponding labels

    Returns:
        {
            "max_divergence_rate": float,
            "pairwise": [{"pair": "A_vs_B", "divergence_rate": float, "divergent": int, "total": int}],
            "num_comparisons": int,
        }
    """
    from scripts.verify_diff import compare_dumps

    pairwise = []
    max_rate = 0.0

    for i in range(len(dumps)):
        for j in range(i + 1, len(dumps)):
            result = compare_dumps(dumps[i], dumps[j], labels[i], labels[j])
            pair_label = f"{labels[i]}_vs_{labels[j]}"
            rate = result["divergence_rate"]
            if rate > max_rate:
                max_rate = rate
            pairwise.append({
                "pair": pair_label,
                "divergence_rate": rate,
                "divergent": result["divergent"],
                "total_checks": result["total_checks"],
                "status": result["status"],
                "section_details": result.get("sections", []),
            })

    return {
        "max_divergence_rate": max_rate,
        "pairwise": pairwise,
        "num_comparisons": len(pairwise),
    }


# ── Metric 3: Policy Instability ────────────────────────────────────


def compute_policy_instability(dumps: list) -> dict:
    """Check whether the same task_type+payload produces different verdicts
    across runs.

    Compares constraint_snapshots across runs keyed by task_id.
    If the same task_id has a different verdict in different runs, that's
    policy instability.

    Returns:
        {
            "instability_rate": float,
            "total_evaluations": int,
            "unstable_count": int,
            "instances": [{"task_id": int, "verdicts": [str]}],
        }
    """
    # Collect snapshots per task_id across runs
    task_verdicts = {}  # task_id → list of (run_index, verdict)
    for run_idx, dump in enumerate(dumps):
        for snap in dump.get("constraint_snapshots", []):
            tid = snap.get("task_id")
            if tid is None:
                continue
            task_verdicts.setdefault(tid, []).append({
                "run": run_idx,
                "verdict": snap.get("verdict", "UNKNOWN"),
            })

    unstable = []
    total = 0
    for tid, verdicts in task_verdicts.items():
        unique_verdicts = list(set(v["verdict"] for v in verdicts))
        total += len(verdicts)
        if len(unique_verdicts) > 1:
            unstable.append({
                "task_id": tid,
                "verdicts": unique_verdicts,
                "per_run": verdicts,
            })

    instability_rate = round(len(unstable) / total, 4) if total > 0 else 0.0
    return {
        "instability_rate": instability_rate,
        "total_evaluations": total,
        "unstable_task_count": len(unstable),
        "instances": unstable[:20],  # cap output
    }


# ── Main ────────────────────────────────────────────────────────────


def compute_all(dump_paths: list) -> dict:
    """Compute all three stability metrics from replay dumps."""
    dumps = [load_dump(p) for p in dump_paths]
    labels = [os.path.splitext(os.path.basename(p))[0] for p in dump_paths]

    # Metric 1: Duplicate execution rate (from first dump — should be identical across runs)
    dup = compute_duplicate_rate(dumps[0])

    # Metric 2: State divergence (pairwise)
    div = compute_divergence_rate(dumps, labels)

    # Metric 3: Policy instability
    inst = compute_policy_instability(dumps)

    # Build verdicts
    results = {
        "duplicate_execution_rate": {
            "value": dup["rate"],
            "target": TARGETS["duplicate_execution_rate"]["label"],
            "target_max": TARGETS["duplicate_execution_rate"]["max"],
            "pass": dup["rate"] <= TARGETS["duplicate_execution_rate"]["max"],
            "details": dup,
        },
        "state_divergence_rate": {
            "value": div["max_divergence_rate"],
            "target": TARGETS["state_divergence_rate"]["label"],
            "target_max": TARGETS["state_divergence_rate"]["max"],
            "pass": div["max_divergence_rate"] <= TARGETS["state_divergence_rate"]["max"],
            "details": div,
        },
        "policy_instability": {
            "value": inst["instability_rate"],
            "target": TARGETS["policy_instability"]["label"],
            "target_max": TARGETS["policy_instability"]["max"],
            "pass": inst["instability_rate"] <= TARGETS["policy_instability"]["max"],
            "details": inst,
        },
    }

    all_pass = all(r["pass"] for r in results.values())

    return {
        "overall_status": "PASS" if all_pass else "FAIL",
        "metrics": results,
        "dumps_compared": len(dump_paths),
        "labels": labels,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/verify_metrics.py run_1.json run_2.json [run_3.json ...]")
        sys.exit(1)

    dump_paths = sys.argv[1:]
    report = compute_all(dump_paths)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Brief summary
    print("\n===== Metrics Summary =====")
    for name, metric in report["metrics"].items():
        status_icon = "PASS" if metric["pass"] else "FAIL"
        print(f"  {name}: {metric['value']} (target: {metric['target']}) [{status_icon}]")
    print(f"\nOverall: {report['overall_status']}")

    sys.exit(0 if report["overall_status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
