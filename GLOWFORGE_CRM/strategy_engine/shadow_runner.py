"""Shadow Runner — 影子模式执行器

在隔离环境中执行完整策略管线，记录决策但不执行任何操作。
支持策略版本对比。

用法:
    from strategy_engine.shadow_runner import run_shadow, compare_versions
    shadow = run_shadow({"market": "US", ...})
    diff = compare_versions("state_v1.json", "state_v2.json")
"""
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("strategy_engine.shadow")

SHADOW_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
)


def _log_shadow(entry):
    """写入影子运行日志"""
    os.makedirs(SHADOW_LOG_DIR, exist_ok=True)
    try:
        with open(os.path.join(SHADOW_LOG_DIR, "shadow_run.log"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def run_shadow(strategy_version="current", customer_context=None):
    """执行影子模式策略分析

    执行完整策略管线但所有输出标记为 dry_run=True，
    只记录决策不执行。

    参数:
        strategy_version: 策略版本标识
        customer_context: 客户上下文（可选）

    返回:
        dict: { shadow_id, timestamp, strategy_version, decisions, ... }
    """
    shadow_id = f"SHADOW-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{hash(str(customer_context)) % 10000:04d}"
    logger.info("Shadow run %s started (version=%s)", shadow_id, strategy_version)

    entry = {
        "shadow_id": shadow_id,
        "timestamp": datetime.now().isoformat(),
        "strategy_version": strategy_version,
        "customer_context": customer_context,
        "dry_run": True,
    }

    # Run strategy analysis
    try:
        from strategy_engine.core.strategy_engine import StrategyEngine
        analysis = StrategyEngine.run_full_analysis(dry_run=True)
        entry["analysis"] = {
            "market_strategy": analysis.get("market_strategy", {}),
            "product_strategy": analysis.get("product_strategy", {}),
            "pricing_strategy": analysis.get("pricing_strategy", {}),
            "recommendations": analysis.get("recommendations", []),
        }
    except Exception as e:
        entry["error"] = f"Strategy analysis failed: {e}"
        logger.warning("Shadow run %s error: %s", shadow_id, e)

    # Check policy for violations
    try:
        from strategy_engine.policy.business_policy import BusinessPolicy
        policy_result = BusinessPolicy.evaluate_strategy(
            entry.get("analysis", {})
        )
        entry["policy_result"] = policy_result
    except Exception as e:
        entry["policy_error"] = str(e)

    _log_shadow(entry)
    logger.info("Shadow run %s complete", shadow_id)
    return entry


def compare_versions(version_a_label, version_b_label,
                     version_a_state=None, version_b_state=None):
    """比较两个策略版本的差异

    参数:
        version_a_label: 版本A的名称
        version_b_label: 版本B的名称
        version_a_state: 版本A的state字典（可选，不传则从shadow日志读取）
        version_b_state: 版本B的state字典（可选）

    返回:
        dict: diff 报告
    """
    if version_a_state is None:
        version_a_state = {}
    if version_b_state is None:
        version_b_state = {}

    diff = {
        "compare": f"{version_a_label} vs {version_b_label}",
        "timestamp": datetime.now().isoformat(),
        "differences": [],
    }

    def _extract(prefix, state):
        markets = state.get("market_strategy", {}).get("top_markets", [])
        products = state.get("product_strategy", {}).get("top_products", [])
        strategies = state.get("pricing_strategy", {}).get("strategies", [])
        return {
            f"{prefix}_markets": [m.get("country_code") for m in markets],
            f"{prefix}_products": [p.get("product_name") for p in products],
            f"{prefix}_pricing_strategies": len(strategies),
        }

    a_data = _extract("a", version_a_state)
    b_data = _extract("b", version_b_state)

    for key in a_data:
        if a_data[key] != b_data[key]:
            diff["differences"].append({
                "field": key,
                "version_a": a_data[key],
                "version_b": b_data[key],
            })

    diff["total_differences"] = len(diff["differences"])
    _log_shadow({
        "type": "version_compare",
        "version_a": version_a_label,
        "version_b": version_b_label,
        "differences": diff["differences"],
    })

    return diff


def get_shadow_history(limit=20):
    """获取最近的影子运行记录

    参数:
        limit: 返回条数

    返回:
        list of dict
    """
    path = os.path.join(SHADOW_LOG_DIR, "shadow_run.log")
    if not os.path.exists(path):
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries[-limit:]
