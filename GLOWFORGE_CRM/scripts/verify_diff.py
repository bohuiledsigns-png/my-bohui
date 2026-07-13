"""V8.5-C2: Diff Checker — compare replay execution dumps for consistency.

Compares two or three replay run dumps field by field, identifying any
divergence in execution state.

Usage:
    python scripts/verify_diff.py run_1.json run_2.json
    python scripts/verify_diff.py run_1.json run_2.json run_3.json

Output:
    JSON report with divergence count, rate, and per-field diffs.

Key principle:
    Deterministic execution means identical state for identical inputs.
    Any divergence is a bug in the execution system.
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
logger = logging.getLogger("verify_diff")

# Fields to compare per entity type
# Timestamps and auto-increment IDs are excluded — they will always differ
COMPARISON_SECTIONS = [
    {
        "key": "execution_queue",
        "label": "Execution Queue",
        "compare_fields": [
            "task_type",
            "status",
            "retry_count",
            "execution_key",
            "error",
        ],
        "id_field": "id",
        "sort_key": "id",
    },
    {
        "key": "constraint_snapshots",
        "label": "Constraint Snapshots",
        "compare_fields": [
            "verdict",
            "reason",
            "satisfiable",
            "blocks_json",
            "holds_json",
            "allows_json",
            "policy_count",
        ],
        "id_field": "id",
        "sort_key": "id",
    },
    {
        "key": "constraint_execution_bindings",
        "label": "Execution Bindings",
        "compare_fields": [
            "snapshot_id",
            "task_id",
            "binding_type",
            "execution_outcome",
        ],
        "id_field": "id",
        "sort_key": "id",
    },
    {
        "key": "execution_dlq",
        "label": "Dead Letter Queue",
        "compare_fields": [
            "original_id",
            "execution_key",
            "task_type",
            "error",
            "retry_count",
        ],
        "id_field": "id",
        "sort_key": "id",
    },
]


def load_dump(path: str) -> dict:
    """Load a replay dump JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compare_value(val_a, val_b, path: str) -> list:
    """Compare two values recursively, returning a list of diff dicts."""
    diffs = []
    if isinstance(val_a, dict) and isinstance(val_b, dict):
        all_keys = set(val_a.keys()) | set(val_b.keys())
        for k in sorted(all_keys):
            sub_path = f"{path}.{k}"
            if k not in val_a:
                diffs.append({
                    "path": sub_path,
                    "type": "missing_in_a",
                    "value_b": val_b[k],
                })
            elif k not in val_b:
                diffs.append({
                    "path": sub_path,
                    "type": "missing_in_b",
                    "value_a": val_a[k],
                })
            else:
                diffs.extend(_compare_value(val_a[k], val_b[k], sub_path))
    elif isinstance(val_a, list) and isinstance(val_b, list):
        if len(val_a) != len(val_b):
            diffs.append({
                "path": path,
                "type": "length_mismatch",
                "len_a": len(val_a),
                "len_b": len(val_b),
            })
        else:
            for i, (ea, eb) in enumerate(zip(val_a, val_b)):
                diffs.extend(_compare_value(ea, eb, f"{path}[{i}]"))
    else:
        # Normalise types for comparison
        sa = str(val_a) if val_a is not None else ""
        sb = str(val_b) if val_b is not None else ""
        if sa != sb:
            diffs.append({
                "path": path,
                "type": "value_mismatch",
                "value_a": val_a,
                "value_b": val_b,
            })
    return diffs


def _compare_trace_logs(trace_a, trace_b, entity_id: int) -> list:
    """Compare trace_log arrays specifically (JSON event sequences)."""
    diffs = []
    if not isinstance(trace_a, list):
        trace_a = []
    if not isinstance(trace_b, list):
        trace_b = []

    if len(trace_a) != len(trace_b):
        diffs.append({
            "path": f"execution_queue[{entity_id}].trace_log",
            "type": "trace_event_count_mismatch",
            "len_a": len(trace_a),
            "len_b": len(trace_b),
        })
        return diffs

    for i, (ea, eb) in enumerate(zip(trace_a, trace_b)):
        # Compare event content (exclude timestamps if present)
        ea_clean = {k: v for k, v in ea.items() if k not in ("t", "ts", "timestamp", "time")}
        eb_clean = {k: v for k, v in eb.items() if k not in ("t", "ts", "timestamp", "time")}
        if ea_clean != eb_clean:
            diffs.append({
                "path": f"execution_queue[{entity_id}].trace_log[{i}]",
                "type": "trace_event_mismatch",
                "value_a": ea_clean,
                "value_b": eb_clean,
            })
    return diffs


def compare_dumps(dump_a: dict, dump_b: dict, label_a: str = "A",
                  label_b: str = "B") -> dict:
    """Compare two replay dumps and return a structured diff report.

    Args:
        dump_a: First replay dump dict
        dump_b: Second replay dump dict
        label_a: Label for first dump (e.g. "run_1")
        label_b: Label for second dump (e.g. "run_2")

    Returns:
        Dict with total_checks, divergent, divergence_rate, failures, sections
    """
    total_checks = 0
    total_divergent = 0
    all_failures = []

    sections = []
    for section_def in COMPARISON_SECTIONS:
        key = section_def["key"]
        entities_a = dump_a.get(key, [])
        entities_b = dump_b.get(key, [])

        section_diffs = []
        compared = 0

        # Build lookup dicts by ID
        by_id_a = {e.get(section_def["id_field"]): e for e in entities_a}
        by_id_b = {e.get(section_def["id_field"]): e for e in entities_b}
        all_ids = sorted(set(by_id_a.keys()) | set(by_id_b.keys()))

        for eid in all_ids:
            ea = by_id_a.get(eid)
            eb = by_id_b.get(eid)

            if ea is None:
                section_diffs.append({
                    "entity_id": eid,
                    "type": "missing_in_first",
                    "value_b": eb.get(section_def["id_field"]),
                })
                total_divergent += 1
                continue
            if eb is None:
                section_diffs.append({
                    "entity_id": eid,
                    "type": "missing_in_second",
                    "value_a": ea.get(section_def["id_field"]),
                })
                total_divergent += 1
                continue

            # Compare defined fields
            for field in section_def["compare_fields"]:
                compared += 1
                va = ea.get(field)
                vb = eb.get(field)
                diffs = _compare_value(va, vb, f"{key}[{eid}].{field}")
                if diffs:
                    section_diffs.extend(diffs)
                    total_divergent += len(diffs)

            # Special: compare trace_log for execution_queue
            if key == "execution_queue":
                tra = ea.get("trace_log")
                trb = eb.get("trace_log")
                trace_diffs = _compare_trace_logs(tra, trb, eid)
                if trace_diffs:
                    section_diffs.extend(trace_diffs)
                    total_divergent += len(trace_diffs)

        total_checks += compared
        sections.append({
            "key": key,
            "label": section_def["label"],
            "compared": compared,
            "entity_count_a": len(entities_a),
            "entity_count_b": len(entities_b),
            "diffs": section_diffs,
            "divergent": len(section_diffs),
        })

    # Also compare queue_summary
    qsa = dump_a.get("queue_summary", {})
    qsb = dump_b.get("queue_summary", {})
    qs_diffs = _compare_value(qsa, qsb, "queue_summary")
    if qs_diffs:
        all_failures.extend(qs_diffs)
        total_divergent += len(qs_diffs)

    divergence_rate = round(
        total_divergent / total_checks, 4
    ) if total_checks > 0 else 0.0

    # Build failure list
    all_failures = []
    for s in sections:
        for d in s["diffs"]:
            all_failures.append(d)
    all_failures.extend(qs_diffs)

    status = "FAIL" if total_divergent > 0 else "PASS"

    return {
        "status": status,
        "total_checks": total_checks,
        "divergent": total_divergent,
        "divergence_rate": divergence_rate,
        "failures": all_failures[:100],  # cap to avoid huge output
        "failure_count": len(all_failures),
        "sections": [
            {
                "key": s["key"],
                "label": s["label"],
                "compared": s["compared"],
                "entity_count_a": s["entity_count_a"],
                "entity_count_b": s["entity_count_b"],
                "divergent": s["divergent"],
            }
            for s in sections
        ],
        "queue_summary_divergent": len(qs_diffs) > 0,
        "label_a": label_a,
        "label_b": label_b,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/verify_diff.py dump_A.json dump_B.json [dump_C.json]")
        sys.exit(1)

    path_a = sys.argv[1]
    path_b = sys.argv[2]
    label_a = os.path.splitext(os.path.basename(path_a))[0]
    label_b = os.path.splitext(os.path.basename(path_b))[0]

    dump_a = load_dump(path_a)
    dump_b = load_dump(path_b)
    result = compare_dumps(dump_a, dump_b, label_a, label_b)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Also compare with C if given
    if len(sys.argv) >= 4:
        path_c = sys.argv[3]
        label_c = os.path.splitext(os.path.basename(path_c))[0]
        dump_c = load_dump(path_c)
        result_c = compare_dumps(dump_a, dump_c, label_a, label_c)
        result_c2 = compare_dumps(dump_b, dump_c, label_b, label_c)
        print("\n--- Comparison with 3rd dump ---")
        print(f"{label_a} vs {label_c}:")
        print(f"  Status: {result_c['status']}, Divergence: {result_c['divergent']}/{result_c['total_checks']} ({result_c['divergence_rate']})")
        print(f"{label_b} vs {label_c}:")
        print(f"  Status: {result_c2['status']}, Divergence: {result_c2['divergent']}/{result_c2['total_checks']} ({result_c2['divergence_rate']})")

    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
