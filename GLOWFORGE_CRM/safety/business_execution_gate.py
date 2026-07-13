"""V8.3 Business Policy Execution Gate — HARD GATE between handler lookup and execution

所有 V8 执行必须先经过此门。3 种输出：
  🟢 ALLOW           → 直接执行
  🔴 BLOCK           → 直接拒绝（带 reason code）
  🟡 HOLD_FOR_REVIEW → 进入人工审核队列

三层架构:
  1. Context Assembly  — ContextBuilder 拼装统一上下文
  2. Policy Evaluation — 结构化策略集，9 evaluators
  3. Conflict Resolution — 优先级冲突解析
"""

import json
import logging
import os
import sqlite3
import time

logger = logging.getLogger("glowforge.business_policy_gate")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ── Verdict constants ──
VERDICT_ALLOW = "ALLOW"
VERDICT_BLOCK = "BLOCK"
VERDICT_HOLD = "HOLD_FOR_REVIEW"

# Evaluator dispatch — maps check_type to method name
_EXECUTION_CHECK_TYPE_DISPATCH = {
    "cancel_blocked": "_evaluate_cancel_blocked",
    "modify_blocked": "_evaluate_modify_blocked",
    "price_change_cooldown": "_evaluate_price_change_cooldown",
    "production_stage_gate": "_evaluate_production_stage_gate",
    "payment_state_gate": "_evaluate_payment_state_gate",
    "auto_action_risk": "_evaluate_auto_action_risk",
    "customer_risk_gate": "_evaluate_customer_risk_gate",
    "contract_term_gate": "_evaluate_contract_term_gate",
    "state_transition_gate": "_evaluate_state_transition_gate",
}


class GateResult:
    """Policy gate evaluation result.

    V8.4: Added `constraints` (ConstraintSet) and `satisfiable` (bool).
    V8.3 fields fully backward compatible.
    """

    def __init__(self, verdict, reason, policy_results=None, context_snapshot=None,
                 constraints=None, satisfiable=True, snapshot_id=None):
        self.verdict = verdict
        self.reason = reason
        self.policy_results = policy_results or []
        self.context_snapshot = context_snapshot or {}
        self.timestamp = time.time()
        # V8.4: constraint set (semantic preservation)
        self.constraints = constraints
        self.satisfiable = satisfiable
        # V8.5-B: constraint snapshot ID (set by CCM after persistence)
        self.snapshot_id = snapshot_id

        # Auto-build constraints from policy_results if not provided
        if self.constraints is None and self.policy_results:
            try:
                from safety.constraint_set import ConstraintSet
                self.constraints = ConstraintSet.from_policy_results(self.policy_results)
            except ImportError:
                pass

    def is_allowed(self):
        return self.verdict == VERDICT_ALLOW

    def is_blocked(self):
        return self.verdict == VERDICT_BLOCK

    def is_hold(self):
        return self.verdict == VERDICT_HOLD

    def to_dict(self):
        d = {
            "verdict": self.verdict,
            "reason": self.reason,
            "policy_count": len(self.policy_results),
            "timestamp": self.timestamp,
        }
        # V8.4: add constraint info if available
        if self.constraints is not None:
            d["constraint_count"] = (
                len(self.constraints.blocks)
                + len(self.constraints.holds)
                + len(self.constraints.allows)
            )
            d["satisfiable"] = self.satisfiable
        return d

    def __repr__(self):
        c_info = ""
        if self.constraints is not None:
            c_info = f" constraints={len(self.constraints.blocks)}B/{len(self.constraints.holds)}H/{len(self.constraints.allows)}A"
        return f"<GateResult {self.verdict}: {self.reason}{c_info}>"


class PolicyResult:
    """Result from a single policy evaluation."""

    def __init__(self, verdict, policy_or_id, reason, severity="hard", priority=500):
        if isinstance(policy_or_id, dict):
            self.policy_id = policy_or_id.get("policy_id", "UNKNOWN")
            self.rule = policy_or_id.get("rule", "")
        else:
            self.policy_id = str(policy_or_id)
            self.rule = ""
        self.verdict = verdict
        self.reason = reason
        self.severity = severity
        self.priority = priority

    def to_dict(self):
        return {
            "policy_id": self.policy_id,
            "rule": self.rule,
            "verdict": self.verdict,
            "reason": self.reason,
            "severity": self.severity,
        }


class BusinessPolicyGate:
    """V8.3 Business Policy Execution Gate — structured, priority-resolved evaluation.

    Reuses V7's `policies` table (category='business_execution') for storage,
    but has its own evaluator dispatch and conflict resolution logic.
    """

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH
        self._context_builder = None  # lazy load
        self._ccm = None  # V8.5-B: lazy load ConstraintCausalMemory

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _get_context_builder(self):
        if self._context_builder is None:
            try:
                from safety.context_builder import ExecutionContextBuilder
                self._context_builder = ExecutionContextBuilder(self._db_path)
            except ImportError:
                self._context_builder = False
        return self._context_builder if self._context_builder is not False else None

    def _get_ccm(self):
        """Lazy-load ConstraintCausalMemory (V8.5-B)."""
        if self._ccm is None:
            try:
                from safety.constraint_causal_memory import ConstraintCausalMemory
                self._ccm = ConstraintCausalMemory(self._db_path)
            except ImportError:
                self._ccm = False    # sentinel: unavailable
        return self._ccm if self._ccm is not False else None

    # ── Public API ──

    def evaluate(self, task_type, payload, customer_id=None, task_id=None):
        """Main entry: evaluate a task against all active business execution policies.

        V8.4: Uses ConstraintSet for semantic preservation + PolicyGraph for
        consistency checking. Falls back to V8.3 _resolve_conflicts if the
        new modules are unavailable.

        V8.5-B: Records constraint snapshot via CCM (fire-and-forget).

        Args:
            task_type: str, e.g. 'cancel_order', 'modify_order', 'change_price'
            payload: dict, the full task payload
            customer_id: int or None
            task_id: int or None (V8.5-B: for snapshot binding)

        Returns:
            GateResult with verdict, reason, policy_results, context_snapshot,
            constraints (V8.4), satisfiable (V8.4), snapshot_id (V8.5-B)
        """
        cid = customer_id or payload.get("customer_id")
        if not cid:
            logger.warning(
                "[Gate] No customer_id for task_type=%s — skipping policy evaluation (ALLOW)",
                task_type,
            )
            return GateResult(VERDICT_ALLOW, "No customer_id — cannot evaluate")

        # Step 1: Build unified context
        ctx = self._get_context_builder()
        context = ctx.build(cid, task_type, payload) if ctx else {}

        # Step 2: Load active business execution policies
        policies = self._load_active_execution_policies()

        # Step 3: Evaluate each relevant policy
        results = []
        for policy in policies:
            if not self._policy_applies_to_action(policy, task_type):
                continue
            result = self._evaluate_single_policy(policy, task_type, payload, context)
            if result is not None:
                results.append(result)

        context_snapshot = {
            "order_status": context.get("order", {}).get("status", ""),
            "production_stage": context.get("production_stage", ""),
            "lead_state": context.get("lead_state", ""),
            "customer_risk": context.get("customer_risk_score", 0),
        }

        # Step 4: V8.4 Constraint Accumulation (with V8.3 fallback)
        try:
            from safety.constraint_set import ConstraintSet
            from safety.constraint_graph import PolicyGraph

            constraint_set = ConstraintSet.from_policy_results(results)
            graph = PolicyGraph.from_policies(policies)

            # Check graph consistency
            if not graph.is_consistent(results):
                logger.info("[BizGate] Policy graph inconsistency detected for %s",
                           task_type)

            result = GateResult(
                verdict=constraint_set.verdict,
                reason=constraint_set.reason,
                policy_results=results,
                context_snapshot=context_snapshot,
                constraints=constraint_set,
                satisfiable=constraint_set.satisfiable,
            )
        except ImportError:
            # V8.3 fallback: _resolve_conflicts (no constraint set)
            final_verdict, final_reason = self._resolve_conflicts(results, task_type)
            result = GateResult(
                verdict=final_verdict,
                reason=final_reason,
                policy_results=results,
                context_snapshot=context_snapshot,
            )

        # V8.5-B: Record constraint snapshot (fire-and-forget)
        ccm = self._get_ccm()
        if ccm is not None:
            try:
                sid = ccm.record_snapshot(
                    gate_result=result,
                    task_id=task_id,
                    customer_id=str(cid) if cid is not None else "",
                    task_type=task_type,
                )
                if sid is not None:
                    result.snapshot_id = sid
            except Exception:
                logger.warning("[BizGate] CCM snapshot recording failed (non-blocking)")

        return result

    def seed_default_policies(self):
        """Seed V8.3 business execution policies into the DB.

        Reuses database.seed_business_execution_policies() for the actual insert.
        Returns number of policies seeded.
        """
        try:
            from database import seed_business_execution_policies
            conn = self._get_conn()
            count = seed_business_execution_policies(conn)
            conn.commit()
            conn.close()
            return count
        except Exception as e:
            logger.warning("[BizGate] seed_default_policies failed: %s", e)
            return 0

    # ── Internal: Policy loading ──

    def _load_active_execution_policies(self):
        """Load policies with category='business_execution' from DB."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT policy_id, category, rule, severity, check_type, "
                "       config_json, priority, version "
                "FROM policies "
                "WHERE category='business_execution' AND is_active=1 "
                "ORDER BY priority ASC",
            ).fetchall()
            conn.close()
            policies = []
            for r in rows:
                d = dict(r)
                try:
                    d["config"] = json.loads(d.get("config_json", "{}"))
                except Exception:
                    d["config"] = {}
                policies.append(d)
            return policies
        except Exception as e:
            logger.warning("[BizGate] _load_policies failed: %s", e)
            return []

    @staticmethod
    def _policy_applies_to_action(policy, task_type):
        """Check if policy's action_domains covers this task_type."""
        config = policy.get("config", {})
        domains = config.get("action_domains", [])
        if not domains or "*" in domains:
            return True
        for domain in domains:
            if domain == task_type:
                return True
            if domain.endswith("*") and task_type.startswith(domain[:-1]):
                return True
        return False

    # ── Internal: Single policy evaluation ──

    def _evaluate_single_policy(self, policy, task_type, payload, context):
        """Evaluate one policy. Returns PolicyResult or None (not applicable)."""
        check_type = policy.get("check_type", "")
        method_name = _EXECUTION_CHECK_TYPE_DISPATCH.get(check_type)
        if method_name is None:
            return None
        method = getattr(self, method_name, None)
        if method is None:
            return None
        try:
            return method(policy, task_type, payload, context)
        except Exception as e:
            logger.warning("[BizGate] Policy %s eval error: %s",
                           policy.get("policy_id", "?"), e)
            return PolicyResult(
                VERDICT_HOLD, policy,
                f"Evaluation error: {e}",
                severity=policy.get("severity", "hard"),
                priority=policy.get("priority", 500),
            )

    # ── Conflict Resolution ──

    @staticmethod
    def _resolve_conflicts(results, task_type):
        """Resolve multiple policy results into a single verdict.

        Rules:
          1. Any BLOCK with severity='hard' -> BLOCK
          2. BLOCK with severity='soft' -> HOLD_FOR_REVIEW
          3. Any HOLD -> HOLD_FOR_REVIEW (if no hard BLOCK)
          4. Only ALLOWs -> ALLOW
          5. Within same verdict, lower priority number wins
        """
        blocks = [r for r in results if r.verdict == VERDICT_BLOCK]
        holds = [r for r in results if r.verdict == VERDICT_HOLD]

        if blocks:
            hard_blocks = [b for b in blocks if b.severity == "hard"]
            if hard_blocks:
                winner = min(hard_blocks, key=lambda r: r.priority)
                return VERDICT_BLOCK, f"策略阻止: {winner.reason}"
            # Only soft blocks -> HOLD
            winner = min(blocks, key=lambda r: r.priority)
            return VERDICT_HOLD, f"需审核: {winner.reason}"

        if holds:
            winner = min(holds, key=lambda r: r.priority)
            return VERDICT_HOLD, f"需审核: {winner.reason}"

        return VERDICT_ALLOW, "全部业务策略通过"

    # ── 9 Evaluators ──

    # BIZ_CANCEL_001
    def _evaluate_cancel_blocked(self, policy, task_type, payload, context):
        """Cancel/Modify blocked for in-production/completed/shipped orders."""
        order = context.get("order", {})
        stage = order.get("status", "")
        config = policy.get("config", {})
        blocked = config.get("blocked_stages", [])

        if stage in blocked:
            deposit_paid = order.get("deposit_received", False)
            if config.get("allow_if_deposit_not_paid") and not deposit_paid:
                return PolicyResult(
                    VERDICT_ALLOW, policy, "订单未付定金，允许取消",
                    priority=policy.get("priority", 50),
                )
            return PolicyResult(
                VERDICT_BLOCK, policy,
                f"订单状态 '{stage}' 禁止取消/修改",
                severity=policy.get("severity", "hard"),
                priority=policy.get("priority", 50),
            )
        return PolicyResult(
            VERDICT_ALLOW, policy, "当前状态允许取消",
            priority=policy.get("priority", 50),
        )

    # BIZ_MODIFY_001
    def _evaluate_modify_blocked(self, policy, task_type, payload, context):
        """Modify blocked for in-production orders unless minor change."""
        order = context.get("order", {})
        stage = order.get("status", "")
        config = policy.get("config", {})
        minor_fields = config.get("minor_changes_allowed_in_production", [])

        if stage == "in_production":
            change_fields = payload.get("change_fields", [])
            if change_fields and all(f in minor_fields for f in change_fields):
                return PolicyResult(
                    VERDICT_ALLOW, policy, "微小修改允许",
                    priority=policy.get("priority", 60),
                )
            if config.get("major_changes_require_approval"):
                return PolicyResult(
                    VERDICT_HOLD, policy,
                    "投产中订单重大修改需人工审核",
                    severity=policy.get("severity", "soft"),
                    priority=policy.get("priority", 60),
                )
        return PolicyResult(
            VERDICT_ALLOW, policy, "当前状态允许修改",
            priority=policy.get("priority", 60),
        )

    # BIZ_PRICE_001
    def _evaluate_price_change_cooldown(self, policy, task_type, payload, context):
        """Cool-down between price changes: 72h + monthly cap."""
        history = context.get("price_change_history", [])
        config = policy.get("config", {})
        cooldown_hours = config.get("cooldown_hours", 72)
        max_per_month = config.get("max_changes_per_month", 3)
        require_approval_above = config.get("require_approval_above_pct", 15)

        # Check monthly cap
        if len(history) >= max_per_month:
            return PolicyResult(
                VERDICT_BLOCK, policy,
                f"本月改价已达 {max_per_month} 次上限",
                severity=policy.get("severity", "hard"),
                priority=policy.get("priority", 100),
            )

        # Check cooldown
        if history:
            try:
                from datetime import datetime as dt
                last = history[0]
                last_time = dt.strptime(
                    last.get("created_at", ""), "%Y-%m-%d %H:%M:%S"
                )
                hours_since = (dt.now() - last_time).total_seconds() / 3600
                if hours_since < cooldown_hours:
                    return PolicyResult(
                        VERDICT_BLOCK, policy,
                        f"距上次改价仅 {hours_since:.0f}h，需冷却 {cooldown_hours}h",
                        severity=policy.get("severity", "hard"),
                        priority=policy.get("priority", 100),
                    )
            except Exception:
                pass

        # Check amount threshold for approval
        new_price = payload.get("price", 0)
        if history and new_price:
            try:
                last_price = history[0].get("total_amount", 0)
                if last_price and last_price > 0:
                    pct_change = abs(new_price - last_price) / last_price * 100
                    if pct_change > require_approval_above:
                        return PolicyResult(
                            VERDICT_HOLD, policy,
                            f"改价幅度 {pct_change:.0f}% 超过 {require_approval_above}%，需审核",
                            severity="soft",
                            priority=policy.get("priority", 100),
                        )
            except Exception:
                pass

        return PolicyResult(
            VERDICT_ALLOW, policy, "改价频率合规",
            priority=policy.get("priority", 100),
        )

    # BIZ_STAGE_001
    def _evaluate_production_stage_gate(self, policy, task_type, payload, context):
        """Gate actions based on production stage transition rules."""
        order = context.get("order", {})
        current_stage = order.get("status", "")
        config = policy.get("config", {})
        blocked_transitions = config.get("blocked_transitions", {})

        blocked_actions = blocked_transitions.get(current_stage, [])
        if task_type in blocked_actions:
            return PolicyResult(
                VERDICT_BLOCK, policy,
                f"生产阶段 '{current_stage}' 禁止操作 '{task_type}'",
                severity=policy.get("severity", "hard"),
                priority=policy.get("priority", 30),
            )
        return PolicyResult(
            VERDICT_ALLOW, policy, "生产阶段允许此操作",
            priority=policy.get("priority", 30),
        )

    # BIZ_PAY_001
    def _evaluate_payment_state_gate(self, policy, task_type, payload, context):
        """Check payment state before allowing production/confirmation."""
        order = context.get("order", {})
        payment = context.get("payment", {})
        config = policy.get("config", {})

        deposit_received = (
            order.get("deposit_received", False)
            or payment.get("deposit_received", False)
        )
        stage = order.get("status", "")

        # Require deposit before production
        if (config.get("require_full_deposit_before_production")
                and stage in ("confirmed", "in_production")
                and not deposit_received):
            return PolicyResult(
                VERDICT_BLOCK, policy,
                "未收到定金不可投产",
                severity=policy.get("severity", "hard"),
                priority=policy.get("priority", 40),
            )

        # Refund check
        if task_type == "refund" and config.get("refund_blocked_if_shipped"):
            if stage in ("shipped", "delivered"):
                return PolicyResult(
                    VERDICT_HOLD, policy,
                    "已发货订单退款需人工审核",
                    severity="soft",
                    priority=policy.get("priority", 40),
                )

        return PolicyResult(
            VERDICT_ALLOW, policy, "支付状态正常",
            priority=policy.get("priority", 40),
        )

    # BIZ_AUTO_001
    def _evaluate_auto_action_risk(self, policy, task_type, payload, context):
        """Risk threshold for automated actions."""
        config = policy.get("config", {})

        # Check auto-discount threshold
        discount = payload.get("discount", 0) or 0
        max_discount = config.get("max_discount_without_review", 10)
        if discount and float(discount) > max_discount:
            return PolicyResult(
                VERDICT_HOLD, policy,
                f"自动折扣 {discount}% 超过 {max_discount}%，需人工审核",
                severity=policy.get("severity", "soft"),
                priority=policy.get("priority", 150),
            )

        # Check customer risk threshold
        customer_risk = context.get("customer_risk_score", 0)
        threshold = config.get(
            "require_human_review_if_customer_risk_above", 0.7
        )
        if isinstance(customer_risk, (int, float)) and customer_risk >= threshold:
            return PolicyResult(
                VERDICT_HOLD, policy,
                f"高风险客户(risk={customer_risk:.2f})，自动操作需审核",
                severity=policy.get("severity", "soft"),
                priority=policy.get("priority", 150),
            )

        return PolicyResult(
            VERDICT_ALLOW, policy, "自动操作风险可接受",
            priority=policy.get("priority", 150),
        )

    # BIZ_RISK_001
    def _evaluate_customer_risk_gate(self, policy, task_type, payload, context):
        """Gate actions based on customer risk score."""
        config = policy.get("config", {})
        risk_score = context.get("customer_risk_score", 0)
        blocked = config.get("high_risk_blocked_actions", [])
        hold = config.get("medium_risk_hold_actions", [])
        severity = policy.get("severity", "hard")

        if not isinstance(risk_score, (int, float)):
            risk_score = 0.0

        if risk_score >= 0.7 and task_type in blocked:
            return PolicyResult(
                VERDICT_BLOCK, policy,
                f"高风险客户({risk_score:.2f})禁止 {task_type}",
                severity=severity,
                priority=policy.get("priority", 20),
            )

        if risk_score >= 0.4 and task_type in hold:
            return PolicyResult(
                VERDICT_HOLD, policy,
                f"中风险客户({risk_score:.2f})需审核 {task_type}",
                severity="soft",
                priority=policy.get("priority", 20),
            )

        return PolicyResult(
            VERDICT_ALLOW, policy, "客户风险可接受",
            priority=policy.get("priority", 20),
        )

    # BIZ_CONTRACT_001
    def _evaluate_contract_term_gate(self, policy, task_type, payload, context):
        """Check contract terms before allowing cancellation/modification/refund."""
        order = context.get("order", {})
        contract_terms = context.get("contract_terms", {})
        config = policy.get("config", {})
        min_amount = config.get("min_order_amount_for_review", 10000)
        total = order.get("total_amount", 0)

        if total >= min_amount:
            # Check if contract has relevant terms
            if not contract_terms or not any(contract_terms.values()):
                return PolicyResult(
                    VERDICT_HOLD, policy,
                    f"大额订单(${total:.0f})无合约条款记录，需人工确认",
                    severity=policy.get("severity", "soft"),
                    priority=policy.get("priority", 80),
                )

            # Check cancellation policy
            cancel_policy = contract_terms.get("cancellation_policy", "")
            if task_type == "cancel_order" and cancel_policy:
                if "no_refund" in cancel_policy or "non-refundable" in cancel_policy:
                    return PolicyResult(
                        VERDICT_HOLD, policy,
                        "合约规定不可退款取消，需人工审核",
                        severity=policy.get("severity", "soft"),
                        priority=policy.get("priority", 80),
                    )

        return PolicyResult(
            VERDICT_ALLOW, policy, "合约条款检查通过",
            priority=policy.get("priority", 80),
        )

    # BIZ_STATE_TRANSITION_001
    def _evaluate_state_transition_gate(self, policy, task_type, payload, context):
        """Validate lead state transitions for state-changing actions."""
        current_state = context.get("lead_state", "NEW")
        config = policy.get("config", {})

        if not config.get("validate_lead_state_transition"):
            return PolicyResult(
                VERDICT_ALLOW, policy, "状态转换验证未启用",
                priority=policy.get("priority", 10),
            )

        # Simple validation: check that the state transition is in machine
        try:
            from execution.kernel import ExecutionStateMachine
            target_state = payload.get("target_lead_state", "")
            if target_state and not ExecutionStateMachine.can_transition(
                current_state, target_state
            ):
                return PolicyResult(
                    VERDICT_BLOCK, policy,
                    f"状态转换 {current_state} -> {target_state} 非法",
                    severity=policy.get("severity", "hard"),
                    priority=policy.get("priority", 10),
                )
        except (ImportError, Exception):
            pass

        return PolicyResult(
            VERDICT_ALLOW, policy, "状态转换合法",
            priority=policy.get("priority", 10),
        )
