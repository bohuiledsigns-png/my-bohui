"""AI Evolution Engine — 销售 AI 持续进化引擎

从 ai_feedback 表读取进化规则 → 注入 AI 策略 → 改变销售行为。
每一条规则都是用户的反馈和测试中发现的问题。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 模块级缓存
_RULES_CACHE = None


def _get_db_rules(active_only=True):
    """从数据库读取规则"""
    sys.path.insert(0, BASE_DIR)
    from database import get_ai_feedback_rules
    return get_ai_feedback_rules(active_only=active_only)


def clear_rules_cache():
    """主动清除缓存（在增/删/改规则后调用）"""
    global _RULES_CACHE
    _RULES_CACHE = None


def get_injected_strategy_blocks(text="", country="", intent=""):
    """生成可注入 _build_sales_strategy 的策略块

    Returns:
        str: 格式化好的规则文本块，直接追加到 strategy 中
    """
    global _RULES_CACHE
    if _RULES_CACHE is None:
        _RULES_CACHE = _get_db_rules(active_only=True)

    if not _RULES_CACHE:
        return ""

    t = text.lower()
    matching_parts = []

    for rule in _RULES_CACHE:
        trigger = (rule.get("trigger_condition") or "").lower()
        if not trigger:
            continue

        # 匹配客户消息关键词
        matched = False
        trigger_str = trigger.strip()

        # 特殊规则：按分类匹配
        cat = rule.get("category", "")

        # 每个规则独立匹配（按 trigger_condition 精确匹配）
        if cat == "b2b_rule":
            if intent in ("询价", "比价", "报价"):
                matched = True
        elif cat == "objection_handling":
            if "比价" in trigger_str and intent == "比价":
                matched = True
            elif "售后" in trigger_str and intent == "售后":
                matched = True
            elif "太贵" in trigger_str and any(w in t for w in ["expensive", "high", "cheap", "budget", "overpriced"]):
                matched = True
        elif cat == "regional_strategy":
            if "中东" in trigger_str and any(w in t for w in ["dubai", "uae", "middle east", "saudi", "qatar", "kuwait", "oman", "bahrain"]):
                matched = True
            elif "欧美" in trigger_str and any(w in t for w in ["europe", "usa", "uk", "germany", "france", "australia", "canada"]):
                matched = True
        elif cat == "sales_tactic":
            if "样品" in trigger_str and intent == "要样品":
                matched = True
            elif "目录" in trigger_str and intent == "要目录":
                matched = True
            elif "交期" in trigger_str and intent == "问交期":
                matched = True
            elif "OEM" in trigger_str and any(w in t for w in ["oem", "partner", "distributor", "bulk", "large volume"]):
                matched = True
            elif "ABC" in trigger_str or "报价结尾" in trigger_str:
                # ABC规则：对所有销售对话生效，防止AI用僵硬的话术模板
                if intent in ("询价", "比价", "问工艺", "要样品", "要目录") or any(w in t for w in ["price", "cost", "quote", "how much"]):
                    matched = True

        # 兜底：关键词包含匹配（仅针对 >=3 字符的英文词或中文词组）
        if not matched:
            # 按空格或逗号分词（不再用 / 分割，避免 A/B/C 误分）
            for sep in [",", ";", "，", "；"]:
                if sep in trigger_str:
                    for word in trigger_str.split(sep):
                        word = word.strip()
                        if len(word) >= 2 and word in t:
                            matched = True
                            break
                    break
            else:
                # 单个短语全匹配
                if len(trigger_str) >= 3 and trigger_str in t:
                    matched = True

        if matched:
            severity_tag = "⚠️ 硬性规则" if rule["severity"] == "hard_rule" else "💡 建议"
            matching_parts.append(
                f"[AI进化-{severity_tag}] {rule.get('action_rule', '')}"
            )

    return "\n\n".join(matching_parts) if matching_parts else ""


def generate_improvements_from_eval(eval_path=None):
    """从评估结果自动生成改进规则

    解析 evaluate_sales_ai.py 输出的 JSON 结果文件，
    对低分场景自动添加进化规则。
    """
    if eval_path and os.path.exists(eval_path):
        import json
        with open(eval_path, "r", encoding="utf-8") as f:
            results = json.load(f)
    else:
        # 尝试最新的评估结果
        eval_dir = os.path.join(BASE_DIR, "eval_results")
        if not os.path.exists(eval_dir):
            return 0
        import glob
        files = sorted(glob.glob(os.path.join(eval_dir, "*.json")))
        if not files:
            return 0
        with open(files[-1], "r", encoding="utf-8") as f:
            results = json.load(f)

    sys.path.insert(0, BASE_DIR)
    from database import add_ai_feedback_rule

    count = 0
    for item in results:
        analysis = item.get("analysis", {})
        scores = analysis.get("scores", {})
        missed = analysis.get("missed_checks", [])

        # 如果 B2B思维 或 主动引导 低于 5，自动生成规则
        if scores.get("B2B思维", 10) < 5 or scores.get("主动引导", 10) < 5:
            scenario_type = item.get("type", "")
            customer_msg = item.get("message", "")[:80]
            if missed:
                rule = "回复前必须执行以下检查:\n" + "\n".join(f"  - {c}" for c in missed)
                add_ai_feedback_rule({
                    "category": "auto_improvement",
                    "trigger_condition": customer_msg,
                    "action_rule": rule,
                    "severity": "suggestion",
                    "source_scenario": f"{item.get('id','?')} {scenario_type}",
                })
                count += 1

    clear_rules_cache()
    return count


if __name__ == "__main__":
    print("=== AI Evolution Engine Test ===")

    # 测试读取
    rules = _get_db_rules()
    print(f"Active rules: {len(rules)}")
    for r in rules:
        print(f"  [{r['severity']}] {r['category']}: {r['trigger_condition']}")

    # 测试匹配
    test_msg = "How much for a set of LED channel letters?"
    result = get_injected_strategy_blocks(text=test_msg, intent="询价")
    print(f"\nMatched blocks for '{test_msg[:50]}...':")
    if result:
        print(result)
    else:
        print("  (none)")
