"""Content Gate — 消息内容审核门

每条出站消息经过三级审核:
  1. Policy Rules — 商业策略规则
  2. Content Safety — 违禁内容检测
  3. Rate Limit — 防御性限速

用法:
    from safety.content_gate import validate_outbound_message
    result = validate_outbound_message("customer_123", "Your price is...", {"tier": "LOW"})
    if not result["passed"]:
        print("Blocked by:", result["blocked_rules"])
"""
import logging
import re
import time

logger = logging.getLogger("glowforge.content_gate")

# ── 违禁模式 ──
_PROHIBITED_PATTERNS = [
    # 密码/敏感信息
    r"(?i)password\s*[=:].{3,}",
    r"(?i)(api[_-]?key|secret)\s*[=:].{3,}",
    # 具有法律约束力的承诺
    r"(?i)guarantee\s+(delivery|shipment).*\d+\s*(hour|day)",
    r"(?i)100%\s*(satisfaction|money.back)",
    # 绝对化价格承诺（物流等因素可能导致变化）
    r"(?i)exactly\s+\$?\d+\.?\d*\s*(delivered|including\s+all\s+tax)",
    # 本地货币汇率承诺
    r"(?i)fixed\s+exchange\s+rate",
]


def _check_policy_rules(message_text, context):
    """检查商业策略规则"""
    blocked = []
    text_lower = message_text.lower()

    # 折扣超标检测
    discount_patterns = re.findall(r"(?i)(\d+)\s*%?\s*off|discount", message_text)
    for match in discount_patterns:
        if isinstance(match, tuple):
            pct = match[0]
        else:
            pct = match
        try:
            pct_val = int(pct)
            if pct_val > 25:
                blocked.append({
                    "policy_id": "POLICY_003",
                    "rule": "最高折扣不得超过25%",
                    "detail": f"检测到 {pct_val}% 折扣",
                    "severity": "hard",
                })
        except (ValueError, TypeError):
            pass

    # 客户等级折扣检查
    tier = context.get("tier", "LOW")
    tier_limits = {"LOW": 5, "MEDIUM": 10, "HIGH_VALUE": 15}
    limit = tier_limits.get(tier, 5)
    for match in re.finditer(r"(?i)(\d+)\s*%", message_text):
        pct = int(match.group(1))
        if pct > limit and tier != "HIGH_VALUE":
            blocked.append({
                "policy_id": "POLICY_004",
                "rule": f"{tier} 客户折扣上限 {limit}%",
                "detail": f"检测到 {pct}% > 上限 {limit}%",
                "severity": "soft",
            })

    return blocked


def _check_content_safety(message_text):
    """检查内容安全性"""
    violations = []
    for pattern in _PROHIBITED_PATTERNS:
        if re.search(pattern, message_text):
            violations.append({
                "rule": "content_prohibited",
                "detail": f"匹配违禁模式: {pattern[:40]}",
                "severity": "hard",
            })
    return violations


def _check_rate_limit(context):
    """防御性限速检查"""
    now = time.time()
    last_send = context.get("_last_send_at", 0)
    min_interval = context.get("min_interval", 5)  # 默认5秒
    if now - last_send < min_interval:
        return [{
            "rule": "rate_limit",
            "detail": f"发送间隔 {now - last_send:.1f}s < 最小 {min_interval}s",
            "severity": "soft",
        }]
    return []


def validate_outbound_message(customer_id, message_text, context=None):
    """对出站消息执行三级审核

    参数:
        customer_id: 客户ID
        message_text: 消息内容
        context: dict，可包含 tier, _last_send_at, min_interval 等

    返回:
        dict: {
            "passed": bool,       # true=通过, false=拦截
            "blocked_rules": [],  # 触发的规则列表
            "modified_text": str or None,  # 自动修改后的文本
            "severity": str,      # hard=硬拦截, soft=警告
            "gate_time_ms": int,  # 审核耗时ms
        }
    """
    if context is None:
        context = {}
    if not message_text:
        return {
            "passed": False,
            "blocked_rules": [{"rule": "empty_message", "detail": "消息为空", "severity": "hard"}],
            "modified_text": None,
            "severity": "hard",
            "gate_time_ms": 0,
        }

    t0 = time.perf_counter()
    all_blocked = []
    severity = "soft"

    # Stage 1: Policy Rules
    policy_hits = _check_policy_rules(message_text, context)
    for hit in policy_hits:
        all_blocked.append(hit)
        if hit.get("severity") == "hard":
            severity = "hard"

    # Stage 2: Content Safety
    safety_hits = _check_content_safety(message_text)
    for hit in safety_hits:
        all_blocked.append(hit)
        if hit.get("severity") == "hard":
            severity = "hard"

    # Stage 3: Rate Limit
    rate_hits = _check_rate_limit(context)
    for hit in rate_hits:
        all_blocked.append(hit)

    gate_time = int((time.perf_counter() - t0) * 1000)
    passed = severity != "hard" and len(all_blocked) == 0

    result = {
        "passed": passed,
        "blocked_rules": all_blocked,
        "modified_text": None,
        "severity": severity,
        "gate_time_ms": gate_time,
    }

    if all_blocked:
        logger.warning(
            "Content gate %s for customer %s: %d rule(s) in %dms",
            "passed" if passed else "BLOCKED",
            customer_id,
            len(all_blocked),
            gate_time,
            extra={"extra_fields": {"customer_id": customer_id, "rules": all_blocked}},
        )

    return result
