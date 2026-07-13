"""V8.4: ConstraintSet — Semantic preservation for policy evaluation results

V8.3 的 _resolve_conflicts() 将多个 BLOCK/HOLD 压缩为单个 verdict + reason，
丢失了"哪些约束同时被触发"的完整语义。

V8.4 ConstraintSet 保留评估的完整语义：
  blocks[] ← 所有 BLOCK（不压缩）
  holds[]  ← 所有 HOLD
  allows[] ← 所有 ALLOW

verdict/reason 从 constraint set 推导，而非从单个 winner 选取。
"""

import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger("glowforge.constraint_set")

VERDICT_ALLOW = "ALLOW"
VERDICT_BLOCK = "BLOCK"
VERDICT_HOLD = "HOLD_FOR_REVIEW"


@dataclass
class Constraint:
    """A single constraint produced by a policy evaluation.

    Maps 1:1 to a PolicyResult, but normalized as a standalone data object
    that doesn't depend on the rest of the gate system.
    """
    policy_id: str
    verdict: str
    reason: str
    severity: str = "hard"
    priority: int = 500

    def __repr__(self):
        return f"<Constraint {self.policy_id}: {self.verdict}({self.severity})>"


class ConstraintSet:
    """Immutable constraint collection — preserves all evaluation semantics.

    Usage:
        cs = ConstraintSet.from_policy_results(results)
        if cs.has_hard_block:
            print(f"BLOCKED: {cs.reason}")
    """

    def __init__(self, blocks=None, holds=None, allows=None):
        self._blocks = list(blocks or [])
        self._holds = list(holds or [])
        self._allows = list(allows or [])

    # ── Public accessors (immutable views) ──

    @property
    def blocks(self) -> List[Constraint]:
        return list(self._blocks)

    @property
    def holds(self) -> List[Constraint]:
        return list(self._holds)

    @property
    def allows(self) -> List[Constraint]:
        return list(self._allows)

    # ── Derived properties ──

    @property
    def has_hard_block(self) -> bool:
        """Any BLOCK with severity='hard'."""
        return any(c.severity == "hard" for c in self._blocks)

    @property
    def has_soft_block(self) -> bool:
        """Any BLOCK with severity='soft'."""
        return any(c.severity == "soft" for c in self._blocks)

    @property
    def verdict(self) -> str:
        """Derive verdict from the full constraint set (not single winner).

        Rules (same as V8.3 _resolve_conflicts, but from set not by selection):
          1. Any hard BLOCK → BLOCK
          2. Any soft BLOCK or any HOLD → HOLD_FOR_REVIEW
          3. Only ALLOWs → ALLOW
        """
        if self.has_hard_block:
            return VERDICT_BLOCK
        if self._holds or self.has_soft_block:
            return VERDICT_HOLD
        return VERDICT_ALLOW

    @property
    def reason(self) -> str:
        """Multi-constraint reason string.

        Format:
          "BLOCK(2): cancelled_in_production; stage_gate_in_production"
          "HOLD(1): large_discount_needs_review"
          "ALLOW: 全部业务策略通过"
        """
        parts = []

        if self._blocks:
            block_msgs = [c.reason for c in self._blocks]
            parts.append(f"BLOCK({len(block_msgs)}): {'; '.join(block_msgs)}")

        if self._holds:
            hold_msgs = [c.reason for c in self._holds]
            parts.append(f"HOLD({len(hold_msgs)}): {'; '.join(hold_msgs)}")

        if not parts:
            return "全部业务策略通过"

        return " | ".join(parts)

    @property
    def satisfiable(self) -> bool:
        """Check if there exists an allowed execution path given constraints.

        Returns False when constraints create a logical conflict:
        - BLOCK and HOLD for the same action with no ALLOW path
        - All possible action types are blocked

        Current implementation: simple check — if all domain-covering
        policies are BLOCK, the set is unsatisfiable.
        """
        # If there are no blocks/holds, trivially satisfiable
        if not self._blocks and not self._holds:
            return True

        # If there's at least one ALLOW, there's a path
        if self._allows:
            return True

        # If only holds (no blocks), satisfiable via review
        if self._holds and not self._blocks:
            return True

        # Hard blocks only — check if there's any non-blocked action
        if self._blocks and not self._allows:
            # All evaluated policies blocked — no clear path
            return False

        return True

    # ── Factory ──

    @classmethod
    def from_policy_results(cls, results: list) -> "ConstraintSet":
        """Build ConstraintSet from a list of PolicyResult objects.

        Each PolicyResult is converted to a Constraint and sorted by verdict.
        """
        blocks, holds, allows = [], [], []

        for r in results:
            c = Constraint(
                policy_id=r.policy_id,
                verdict=r.verdict,
                reason=r.reason,
                severity=r.severity,
                priority=r.priority,
            )
            if r.verdict == VERDICT_BLOCK:
                blocks.append(c)
            elif r.verdict == VERDICT_HOLD:
                holds.append(c)
            else:
                allows.append(c)

        return cls(blocks=blocks, holds=holds, allows=allows)

    # ── Operations ──

    def merge(self, other: "ConstraintSet") -> "ConstraintSet":
        """Merge two constraint sets (union of all constraints)."""
        return ConstraintSet(
            blocks=self._blocks + other._blocks,
            holds=self._holds + other._holds,
            allows=self._allows + other._allows,
        )

    def to_dict(self, max_per_type=50) -> dict:
        """Serialize this ConstraintSet to a JSON-safe dict.

        V8.5-B: Persistence bridge — serializes constraint state for
        database storage. Each constraint becomes a plain dict.

        Args:
            max_per_type: Max constraints per verdict type (prevents
                          pathological row sizes). Default 50.

        Returns:
            dict with keys: verdict, reason, satisfiable, blocks, holds, allows
        """
        def _ser(constraints):
            return [
                {
                    "policy_id": c.policy_id,
                    "verdict": c.verdict,
                    "reason": c.reason,
                    "severity": c.severity,
                    "priority": c.priority,
                }
                for c in list(constraints)[:max_per_type]
            ]

        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "satisfiable": self.satisfiable,
            "blocks": _ser(self._blocks),
            "holds": _ser(self._holds),
            "allows": _ser(self._allows),
        }

    def to_gate_result(self, context_snapshot=None):
        """Convert to GateResult (lazy import to avoid circular dependency)."""
        from safety.business_execution_gate import GateResult
        return GateResult(
            verdict=self.verdict,
            reason=self.reason,
            policy_results=[],
            context_snapshot=context_snapshot or {},
            constraints=self,
            satisfiable=self.satisfiable,
        )

    def __repr__(self):
        return (
            f"<ConstraintSet blocks={len(self._blocks)} "
            f"holds={len(self._holds)} "
            f"allows={len(self._allows)} "
            f"verdict={self.verdict}>"
        )
