"""Execution Firewall — 执行防火墙

所有 AI 动作的唯一入口。在 decide_action 之后、执行之前拦截。
执行 5 项检查后返回 verdict: ALLOW | BLOCK | MODIFY | FLAG

检查顺序:
  1. Policy Check — BusinessPolicy 硬规则（国家/折扣/利润率）
  2. Price Consistency — 历史报价偏差检测（±10%）
  3. State Consistency — 动作/状态兼容性矩阵
  4. Agent Conflict — 多 Agent 价格冲突检测
  5. Risk Assessment — 风险评估

用法:
    from safety.execution_firewall import ExecutionFirewall
    fw = ExecutionFirewall()
    decision = fw.check(customer_id, action, context)
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime

logger = logging.getLogger("glowforge.execution_firewall")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# BusinessPolicy 规则缓存（延迟加载）
_POLICY_RULES = None


def _load_policy_rules():
    """加载 BusinessPolicy 规则（懒加载）"""
    global _POLICY_RULES
    if _POLICY_RULES is not None:
        return _POLICY_RULES
    try:
        from strategy_engine.policy.business_policy import POLICY_RULES
        _POLICY_RULES = POLICY_RULES
    except ImportError:
        _POLICY_RULES = []
    return _POLICY_RULES


# 违禁内容模式（与 content_gate 共享）
_PROHIBITED_PATTERNS = [
    re.compile(r"(?i)password\s*[=:].{3,}"),
    re.compile(r"(?i)(api[_-]?key|secret)\s*[=:].{3,}"),
    re.compile(r"(?i)guarantee\s+(delivery|shipment).*\d+\s*(hour|day)"),
    re.compile(r"(?i)100%\s*(satisfaction|money.back)"),
    re.compile(r"(?i)fixed\s+exchange\s+rate"),
]

# 报价金额正则（用于从消息中提取价格）
_PRICE_PATTERN = re.compile(r"\$?\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(USD|usd|美元)?")
_DISCOUNT_PATTERN = re.compile(r"(\d+)\s*%")


class ExecutionFirewall:
    """执行防火墙 — AI 动作的宪法法院"""

    def __init__(self, registry=None, base_dir=None):
        self.base_dir = base_dir or BASE_DIR
        self._registry = registry
        self.log_path = os.path.join(self.base_dir, "logs", "execution_firewall.log")
        # 延迟创建：首次写日志时建目录（见 _log_decision）

    def _get_registry(self):
        """延迟获取 StateRegistry（避免循环导入）"""
        if self._registry is None:
            from safety.state_registry import StateRegistry
            self._registry = StateRegistry(self.base_dir)
        return self._registry

    def check(self, customer_id, action, context=None):
        """主入口：执行全部 5 项检查，返回决策

        参数:
            customer_id: 客户ID
            action: {
                "type": "send_reply|send_quote|send_negotiation|...",
                "content": str,           # AI 生成的消息内容
                "price": float or None,   # 报价金额（如有）
                "discount": float or None, # 折扣比例（如有）
                "intent": str,            # 意图分类
                "source_agent": str,      # 来源 Agent
            }
            context: {
                "translation": str,
                "urgency": str,
                "customer_country": str,
                "customer_tier": str,
            }

        返回:
            dict: {verdict, reason, modified_action, risk_score, checks, decision_id, timestamp}
        """
        if context is None:
            context = {}
        t0 = datetime.now()

        checks = {}
        decision_id = f"FW-{uuid.uuid4().hex[:12].upper()}"
        blocked_rules = []
        modified = False
        verdict = "ALLOW"

        # 获取统一状态
        registry = self._get_registry()
        unified_state = registry.get_unified_state(customer_id)

        # 推断 intent → action_type（如果未指定）
        action_type = action.get("type", "send_reply")
        if action_type == "send_reply":
            intent = action.get("intent", context.get("intent", ""))
            from safety.state_registry import INTENT_TO_ACTION
            action_type = INTENT_TO_ACTION.get(intent, "send_followup")

        action_payload = {
            "type": action_type,
            "intent": action.get("intent"),
            "content": action.get("content", "")[:200],
        }

        # ── 1. Policy Check ──
        policy_result = self._check_policy(action, context, unified_state)
        checks["policy"] = policy_result
        if not policy_result["passed"]:
            blocked_rules.extend(policy_result.get("rules", []))
            if any(r.get("severity") == "hard" for r in policy_result.get("rules", [])):
                verdict = "BLOCK"

        # ── 2. Price Consistency ──
        price_result = self._check_price_consistency(action, unified_state)
        checks["price_consistency"] = price_result
        if not price_result["passed"]:
            blocked_rules.extend(price_result.get("rules", []))
            if verdict != "BLOCK":
                verdict = "FLAG"

        # ── 3. State Consistency ──
        state_result = self._check_state_consistency(action_type, unified_state)
        checks["state_consistency"] = state_result
        if not state_result["passed"]:
            blocked_rules.extend(state_result.get("rules", []))
            if verdict != "BLOCK":
                verdict = "BLOCK" if state_result.get("matrix_result") == "BLOCK" else "MODIFY"
                if state_result.get("matrix_result") == "MODIFY":
                    modified = True

        # ── 4. Agent Conflict ──
        agent_result = self._check_agent_conflict(action, unified_state)
        checks["agent_conflict"] = agent_result
        if not agent_result["passed"]:
            blocked_rules.extend(agent_result.get("rules", []))
            if verdict != "BLOCK":
                has_hard = any(r.get("severity") == "hard" for r in agent_result.get("rules", []))
                verdict = "BLOCK" if has_hard else "FLAG"

        # ── 5. Risk Assessment ──
        risk_result = self._assess_risk(action_type, action, context)
        checks["risk_assessment"] = risk_result
        _v7_risk_continuous = risk_result.get("continuous_score", None)
        if risk_result.get("level") == "critical" and verdict == "ALLOW":
            verdict = "FLAG"

        # ── 6. Graph Profit Path Check (V7) ──
        graph_result = self._check_graph_profit_path(customer_id, action, context)
        checks["graph_profit_path"] = graph_result
        _graph_adj = graph_result.get("graph_adjustment", 0.0)
        if _graph_adj and _v7_risk_continuous is not None:
            _v7_risk_continuous = max(0.0, min(1.0, _v7_risk_continuous + _graph_adj))

        # ── V7: ESCALATE verdict for medium-high continuous risk ──
        _escalate_score = _v7_risk_continuous if _v7_risk_continuous is not None else None
        if _escalate_score is not None and verdict == "ALLOW":
            if _escalate_score >= 0.7:
                verdict = "BLOCK"
            elif _escalate_score >= 0.3:
                verdict = "ESCALATE"

        # ── 修正建议 ──
        modified_action = None
        if modified or verdict == "MODIFY":
            modified_action = self._generate_modification(action, checks, unified_state)

        # ── 最终决策 ──
        decision = {
            "decision_id": decision_id,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": int((datetime.now() - t0).total_seconds() * 1000),
            "customer_id": customer_id,
            "verdict": verdict,
            "reason": self._summarize_reason(verdict, checks, blocked_rules),
            "risk_score": risk_result.get("level", "low"),
            "risk_score_continuous": _v7_risk_continuous if _v7_risk_continuous is not None else risk_result.get("continuous_score", 0.0),
            "checks": checks,
            "blocked_rules": blocked_rules,
            "modified_action": modified_action,
            "action": action_payload,
        }

        # 记录到日志
        self._log_decision(decision)

        # 注册到 WAL
        if verdict != "BLOCK":
            try:
                registry.register_action(
                    customer_id, action_type, {
                        "verdict": verdict,
                        "decision_id": decision_id,
                        "risk": risk_result.get("level"),
                        "content_preview": action.get("content", "")[:100],
                    }
                )
            except Exception:
                pass

        return decision

    def _check_policy(self, action, context, unified_state):
        """Policy Check — BusinessPolicy 硬规则 (V7: PolicyEngine if available)"""
        rules = []
        content = action.get("content", "")

        # V7: Try PolicyEngine first for DB-backed policies
        try:
            from safety.policy_engine import PolicyEngine
            pe = PolicyEngine()
            if pe is not None:
                db_result = pe.check_policies(action, context, unified_state)
                if db_result.get("policies_loaded", False):
                    for v in db_result.get("rules", []):
                        if not any(r.get("policy_id") == v.get("policy_id") for r in rules):
                            rules.append(v)
        except Exception:
            pass
        discount = action.get("discount")
        price = action.get("price")
        country = context.get("customer_country", "")
        tier = context.get("customer_tier", "LOW")

        # POLICY_003: 折扣 ≤ 25%
        if discount is not None and discount > 25:
            rules.append({
                "policy_id": "POLICY_003",
                "rule": "最高折扣不得超过25%",
                "detail": f"折扣 {discount}% 超过上限 25%",
                "severity": "hard",
            })

        # 从内容中提取折扣
        if discount is None:
            for match in _DISCOUNT_PATTERN.finditer(content):
                pct = int(match.group(1))
                if pct > 25:
                    rules.append({
                        "policy_id": "POLICY_003",
                        "rule": "最高折扣不得超过25%",
                        "detail": f"内容含 {pct}% 折扣超过上限 25%",
                        "severity": "hard",
                    })

        # POLICY_004: 客户等级折扣
        tier_limits = {"LOW": 5, "MEDIUM": 10, "HIGH_VALUE": 15}
        limit = tier_limits.get(tier, 5)
        check_discount = discount or 0
        for match in _DISCOUNT_PATTERN.finditer(content):
            pct = int(match.group(1))
            if pct > limit and tier != "HIGH_VALUE":
                rules.append({
                    "policy_id": "POLICY_004",
                    "rule": f"{tier} 客户折扣上限 {limit}%",
                    "detail": f"折扣 {pct}% > {tier} 上限 {limit}%",
                    "severity": "soft",
                })

        # POLICY_001: 国家限制
        if country:
            try:
                from strategy_engine.policy.business_policy import POLICY_RULES
                for rule in POLICY_RULES:
                    if rule.get("check_type") == "country_allowed" and rule.get("allowed_countries"):
                        if country not in rule["allowed_countries"]:
                            rules.append({
                                "policy_id": "POLICY_001",
                                "rule": "市场不在许可范围",
                                "detail": f"国家 {country} 不在许可列表",
                                "severity": "hard",
                            })
            except ImportError:
                pass

        # 违禁内容检测
        for pattern in _PROHIBITED_PATTERNS:
            if pattern.search(content):
                rules.append({
                    "policy_id": "CONTENT_001",
                    "rule": "违禁内容",
                    "detail": f"匹配违禁模式: {pattern.pattern[:40]}",
                    "severity": "hard",
                })

        passed = not any(r.get("severity") == "hard" for r in rules)
        return {"passed": passed, "rules": rules, "total": len(rules)}

    def _check_price_consistency(self, action, unified_state):
        """Price Consistency — 历史报价偏差检测"""
        rules = []
        price = action.get("price")
        if price is None:
            # 从内容中提取价格
            matches = _PRICE_PATTERN.findall(action.get("content", ""))
            if matches:
                try:
                    price = float(matches[0][0].replace(",", ""))
                except (ValueError, IndexError):
                    price = None

        if price is None:
            return {"passed": True, "rules": [], "detail": "无价格信息可检查"}

        history = unified_state.get("pricing_history", [])
        if not history:
            return {"passed": True, "rules": [], "detail": "首次报价"}

        # 检查最近报价偏差
        last_quote = history[0]
        last_price = last_quote.get("amount")
        if last_price and last_price > 0:
            deviation = abs(price - last_price) / last_price
            if deviation > 0.10:
                rules.append({
                    "policy_id": "PRICE_001",
                    "rule": "报价偏差超过 ±10%",
                    "detail": f"新报价 {price} vs 上次 {last_price} (偏差 {deviation:.1%})",
                    "severity": "hard",
                    "last_quote_id": last_quote.get("quote_id"),
                })

        # 检查待处理报价（pending 状态下不能改价）
        pending = [q for q in history if q.get("status") == "pending"]
        if pending and rules:
            rules[0]["detail"] += " — 上一报价仍待处理"

        return {
            "passed": len(rules) == 0,
            "rules": rules,
            "detail": f"价格一致性: {price} vs 历史均价",
            "detected_price": price,
        }

    def _check_state_consistency(self, action_type, unified_state):
        """State Consistency — 动作/状态兼容性矩阵"""
        sync_state = unified_state.get("sync_state", "NEW")

        from safety.state_registry import ACTION_STATE_MATRIX
        matrix = ACTION_STATE_MATRIX.get(action_type, {})
        matrix_result = matrix.get(sync_state, "BLOCK")

        if matrix_result == "ALLOW":
            return {
                "passed": True,
                "matrix_result": "ALLOW",
                "reason": None,
                "rules": [],
            }
        elif matrix_result == "MODIFY":
            return {
                "passed": True,
                "matrix_result": "MODIFY",
                "reason": f"{action_type} 在 {sync_state} 下受限但可执行",
                "rules": [{
                    "policy_id": "STATE_001",
                    "rule": "动作/状态兼容性",
                    "detail": f"{action_type} → {sync_state} = MODIFY",
                    "severity": "soft",
                }],
            }
        else:
            return {
                "passed": False,
                "matrix_result": "BLOCK",
                "reason": f"{action_type} 不允许在 {sync_state} 状态下执行",
                "rules": [{
                    "policy_id": "STATE_001",
                    "rule": "动作/状态兼容性",
                    "detail": f"{action_type} → {sync_state} = BLOCK",
                    "severity": "hard",
                }],
            }

    def _check_agent_conflict(self, action, unified_state):
        """Agent Conflict — 多 Agent 冲突检测

        使用 AgentCoordinator 的锁状态 + 价格 Oracle 升级冲突检查：
          - 锁冲突 → BLOCK (hard)
          - 价格与 Oracle 锚点偏差 >10% → BLOCK (hard)
          - 跨 Agent 历史报价偏差 >10% → BLOCK (hard，原为 soft)
        """
        rules = []
        source = action.get("source_agent", "unknown")
        price = action.get("price")
        customer_id = unified_state.get("customer_id")
        coordinator = None

        # 1. Coordinator 锁冲突检查
        try:
            from safety.agent_coordinator import AgentCoordinator
            coordinator = AgentCoordinator(self._registry)
            current_agent = coordinator.get_current_agent(customer_id)
            if current_agent and current_agent != source:
                rules.append({
                    "policy_id": "AGENT_002",
                    "rule": "Agent 锁冲突",
                    "detail": f"{source} 尝试操作被 {current_agent} 锁定的客户",
                    "severity": "hard",
                })
        except ImportError:
            pass
        except Exception:
            pass

        # 2. 价格 Oracle 检查（重用 coordinator 实例，避免重复创建）
        if price:
            try:
                if coordinator is None:
                    from safety.agent_coordinator import AgentCoordinator
                    coordinator = AgentCoordinator(self._registry)
                oracle = coordinator.get_price_oracle(customer_id)
                if oracle:
                    for tier_key, tier_data in oracle.items():
                        if isinstance(tier_data, dict):
                            for anchor_key, anchor_val in tier_data.items():
                                if isinstance(anchor_val, (int, float)) and anchor_val > 0:
                                    deviation = abs(price - anchor_val) / anchor_val
                                    if deviation > 0.10:
                                        rules.append({
                                            "policy_id": "PRICE_002",
                                            "rule": "价格与 Oracle 锚点偏差 >10%",
                                            "detail": f"{source} 报价 {price} 偏离锚点 {anchor_key}={anchor_val} ({deviation:.1%})",
                                            "severity": "hard",
                                        })
            except Exception:
                pass

        # 3. 从 WAL 获取最近同客户的动作（升级为 hard）
        try:
            registry = self._get_registry()
            recent = registry.get_wal_history(customer_id, limit=20)
            agent_prices = {}
            for entry in recent:
                payload = entry.get("payload", {})
                if payload.get("source_agent") and payload.get("source_agent") != source:
                    agent_prices[payload.get("source_agent", "?")] = payload.get("price")

            if agent_prices and price:
                for agent_name, agent_price in agent_prices.items():
                    if agent_price and abs(price - agent_price) / max(price, agent_price) > 0.10:
                        rules.append({
                            "policy_id": "AGENT_001",
                            "rule": "Agent 报价冲突",
                            "detail": f"{source} 报价 {price} 与 {agent_name} 报价 {agent_price} 偏差 >10%",
                            "severity": "hard",
                        })
        except Exception:
            pass

        return {"passed": len(rules) == 0, "rules": rules}

    def _assess_risk(self, action_type, action, context):
        """Risk Assessment — V7 continuous scoring with 3-level fallback"""
        from safety.state_registry import ACTION_RISK
        base_risk = ACTION_RISK.get(action_type, "low")

        # V7: Try RiskEngine for continuous scoring
        _continuous_score = None
        _risk_dimensions = None
        try:
            from safety.risk_engine import RiskEngine
            re = RiskEngine()
            if re is not None:
                # customer_id needed for RiskEngine scoring — use context if available
                cid = action.get("customer_id") or context.get("customer_id")
                risk_result = re.score(cid, action, context)
                _continuous_score = risk_result.get("overall")
                _risk_dimensions = risk_result.get("dimensions")
        except Exception:
            pass

        factors = []
        urgency = context.get("urgency", "低")

        # 提权因素
        if action_type in ("send_quote", "send_negotiation"):
            factors.append("涉及金额和利润")
        if action.get("discount") and action["discount"] > 10:
            factors.append(f"折扣 {action['discount']}% 超过10%")
            if base_risk == "medium":
                base_risk = "high"
        if urgency == "高":
            factors.append("高紧迫性场景")

        result = {"level": base_risk, "factors": factors}
        if _continuous_score is not None:
            result["continuous_score"] = _continuous_score
            result["dimensions"] = _risk_dimensions
        return result

    def _check_graph_profit_path(self, customer_id, action, context):
        """V7: Graph profit path check — advisory risk modifier"""
        try:
            from safety.graph_check import GraphCheck
            gc = GraphCheck()
            if gc is not None:
                return gc.check(customer_id, action, context)
            return {"graph_available": False, "graph_adjustment": 0.0}
        except Exception:
            return {"graph_available": False, "graph_adjustment": 0.0}

    def _generate_modification(self, action, checks, unified_state):
        """自动修正动作（MODIFY 时调用）"""
        modified = dict(action)

        # 折扣修正：超限折扣降到上限
        content = modified.get("content", "")
        new_content = content
        for match in _DISCOUNT_PATTERN.finditer(content):
            pct = int(match.group(1))
            if pct > 25:
                new_content = new_content.replace(match.group(0), "25%", 1)

        if new_content != content:
            modified["content"] = new_content
            modified["_modified"] = True
            modified["_modification_note"] = "折扣上限修正: >25% → 25%"
            modified["discount"] = 25

        return modified

    def _summarize_reason(self, verdict, checks, blocked_rules):
        """生成人类可读的决策原因"""
        if verdict == "ALLOW":
            return "全部检查通过"
        elif verdict == "BLOCK":
            reasons = [r["detail"] for r in blocked_rules[:3]]
            return "拦截: " + "; ".join(reasons)
        elif verdict == "MODIFY":
            return "已自动修正: " + (checks.get("state_consistency", {}).get("reason") or "内容修正")
        elif verdict == "ESCALATE":
            reasons = [r["detail"] for r in blocked_rules[:2]]
            return "需升级审核: " + "; ".join(reasons) if reasons else "需升级审核: 风险评分中等偏高"
        elif verdict == "FLAG":
            return "需审查: " + (checks.get("price_consistency", {}).get("detail") or "价格异常")
        return "未知决策"

    def _log_decision(self, decision):
        """记录决策到日志文件 + V7 AuditLogger"""
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(decision, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
        try:
            from safety.audit_logger import AuditLogger
            al = AuditLogger()
            if al is not None:
                al.log_decision(decision)
        except Exception:
            pass

    def get_recent_decisions(self, customer_id=None, limit=50):
        """获取最近决策记录"""
        if not os.path.exists(self.log_path):
            return []
        decisions = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if customer_id is None or d.get("customer_id") == customer_id:
                            decisions.append(d)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return decisions[-limit:]
