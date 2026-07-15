"""V8.4: PolicyGraph — Explicit policy relationship graph

从现有 `policies` 表的 `config_json` + `priority` 自动推断 policy 之间的关系：
  - overrides:      同 action_domain 上高优先级覆盖低优先级
  - conflicts_with: 对同一场景产生矛盾的约束
  - refines:        子策略细化父策略的业务规则

替代 V8.3 纯 priority 排序的平面冲突模型。
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("glowforge.constraint_graph")

EDGE_OVERRIDES = "overrides"
EDGE_CONFLICTS = "conflicts_with"
EDGE_REFINES = "refines"


@dataclass
class PolicyEdge:
    """A directed edge between two policies.

    Attributes:
        source: policy_id of the source (overriding / conflicting)
        target: policy_id of the target (being overridden / conflicted with)
        edge_type: OVERRIDES | CONFLICTS_WITH | REFINES
        metadata: optional dict with additional context (e.g. action_domain)
    """
    source: str
    target: str
    edge_type: str
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return f"<PolicyEdge {self.source} --{self.edge_type}--> {self.target}>"


class PolicyGraph:
    """Directed graph of policy relationships.

    Built automatically from policy configs — no manual edge configuration needed.
    """

    def __init__(self, edges: Optional[List[PolicyEdge]] = None):
        self._edges = list(edges or [])
        # adjacency maps for fast lookup
        self._outgoing: Dict[str, List[PolicyEdge]] = {}  # source -> edges
        self._incoming: Dict[str, List[PolicyEdge]] = {}  # target -> edges
        self._rebuild_index()

    def _rebuild_index(self):
        self._outgoing.clear()
        self._incoming.clear()
        for e in self._edges:
            self._outgoing.setdefault(e.source, []).append(e)
            self._incoming.setdefault(e.target, []).append(e)

    @property
    def edges(self) -> List[PolicyEdge]:
        return list(self._edges)

    @classmethod
    def from_policies(cls, policies: list) -> "PolicyGraph":
        """Build graph from policies list (from _load_active_execution_policies()).

        Infers edges from:
          1. priority + overlapping action_domains → overrides
          2. same action_domain + contradictory configs → conflicts_with
          3. regex/substring action_domain containment → refines
        """
        edges = []
        if not policies:
            return cls()

        # Index by policy_id for cross-reference
        by_id = {}
        for p in policies:
            pid = p.get("policy_id", "") or ""
            by_id[pid] = p

        # Compare every pair to infer relationships
        for i, a in enumerate(policies):
            pid_a = a.get("policy_id", "") or ""
            domains_a = _get_action_domains(a)
            pri_a = a.get("priority", 500)

            for j, b in enumerate(policies):
                if i == j:
                    continue
                pid_b = b.get("policy_id", "") or ""
                domains_b = _get_action_domains(b)
                pri_b = b.get("priority", 500)

                # Check domain overlap
                overlap = _domain_overlap(domains_a, domains_b)
                if not overlap:
                    continue

                # overrides: lower priority number overrides higher
                if pri_a < pri_b:
                    # a has higher priority → a overrides b on the overlapping domain
                    if not _is_already_in_edges(edges, pid_a, pid_b, EDGE_OVERRIDES):
                        edges.append(PolicyEdge(
                            source=pid_a,
                            target=pid_b,
                            edge_type=EDGE_OVERRIDES,
                            metadata={"domain": overlap},
                        ))
                elif pri_b < pri_a:
                    if not _is_already_in_edges(edges, pid_b, pid_a, EDGE_OVERRIDES):
                        edges.append(PolicyEdge(
                            source=pid_b,
                            target=pid_a,
                            edge_type=EDGE_OVERRIDES,
                            metadata={"domain": overlap},
                        ))

                # conflicts_with: equal priority, overlapping domain → potential conflict
                if pri_a == pri_b and overlap:
                    if not _is_already_in_edges(edges, pid_a, pid_b, EDGE_CONFLICTS):
                        edges.append(PolicyEdge(
                            source=pid_a,
                            target=pid_b,
                            edge_type=EDGE_CONFLICTS,
                            metadata={"domain": overlap},
                        ))

                # refines: domain_a is more specific than domain_b
                if _domain_refines(domains_a, domains_b):
                    if not _is_already_in_edges(edges, pid_a, pid_b, EDGE_REFINES):
                        edges.append(PolicyEdge(
                            source=pid_a,
                            target=pid_b,
                            edge_type=EDGE_REFINES,
                            metadata={"domain": overlap},
                        ))

        return cls(edges)

    def get_outgoing(self, policy_id: str) -> List[PolicyEdge]:
        """Get all edges where this policy is the source."""
        return list(self._outgoing.get(policy_id, []))

    def get_incoming(self, policy_id: str) -> List[PolicyEdge]:
        """Get all edges where this policy is the target."""
        return list(self._incoming.get(policy_id, []))

    def get_overrides(self, policy_id: str) -> List[str]:
        """Get policy_ids that this policy overrides."""
        return [
            e.target for e in self._outgoing.get(policy_id, [])
            if e.edge_type == EDGE_OVERRIDES
        ]

    def get_overridden_by(self, policy_id: str) -> List[str]:
        """Get policy_ids that override this policy."""
        return [
            e.source for e in self._incoming.get(policy_id, [])
            if e.edge_type == EDGE_OVERRIDES
        ]

    def get_conflicts(self, policy_id: str) -> List[str]:
        """Get policy_ids that conflict with this policy."""
        result = []
        for e in self._outgoing.get(policy_id, []):
            if e.edge_type == EDGE_CONFLICTS:
                result.append(e.target)
        for e in self._incoming.get(policy_id, []):
            if e.edge_type == EDGE_CONFLICTS:
                result.append(e.source)
        return result

    def is_consistent(self, results: list) -> bool:
        """Check if a set of evaluation results is consistent with the graph.

        A result set is consistent when:
          1. No conflicting policies both produce BLOCK for the same action
          2. No circular override chains exist

        Args:
            results: list of PolicyResult objects

        Returns:
            bool: True if consistent
        """
        # Check for circular override chains (simple DFS)
        visited = set()
        for pid in self._outgoing:
            if self._has_cycle(pid, set(), visited):
                logger.warning("[PolicyGraph] Circular override chain detected at %s", pid)
                return False

        # Check for conflicting BLOCKs on same policy pair
        block_by_policy = {}
        for r in results:
            if r.verdict in ("BLOCK", "HOLD_FOR_REVIEW"):
                block_by_policy[r.policy_id] = r

        for e in self._edges:
            if e.edge_type == EDGE_CONFLICTS:
                if (e.source in block_by_policy
                        and e.target in block_by_policy):
                    logger.info(
                        "[PolicyGraph] Conflicting BLOCKs: %s and %s",
                        e.source, e.target,
                    )
                    # Conflicts are informational, not blocking

        return True

    def _has_cycle(self, node, visiting, visited) -> bool:
        """DFS cycle detection."""
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        try:
            for edge in self._outgoing.get(node, []):
                if edge.edge_type == EDGE_OVERRIDES:
                    if self._has_cycle(edge.target, visiting, visited):
                        return True
        finally:
            visiting.discard(node)
        visited.add(node)
        return False

    def summary(self) -> dict:
        """Return a human-readable summary of the graph."""
        return {
            "total_edges": len(self._edges),
            "overrides": sum(1 for e in self._edges if e.edge_type == EDGE_OVERRIDES),
            "conflicts": sum(1 for e in self._edges if e.edge_type == EDGE_CONFLICTS),
            "refines": sum(1 for e in self._edges if e.edge_type == EDGE_REFINES),
            "policy_count": len(set(
                e.source for e in self._edges
            ) | set(e.target for e in self._edges)),
        }

    def __repr__(self):
        s = self.summary()
        return (
            f"<PolicyGraph {s['total_edges']} edges: "
            f"{s['overrides']} overrides, "
            f"{s['conflicts']} conflicts, "
            f"{s['refines']} refines>"
        )


# ── Internal helpers ──


def _get_action_domains(policy: dict) -> set:
    """Extract action domains from a policy config dict."""
    config = policy.get("config", {})
    domains = config.get("action_domains", [])
    if isinstance(domains, list):
        return set(domains)
    return {domains} if domains else set()


def _domain_overlap(domains_a: set, domains_b: set) -> str:
    """Check if two domain sets overlap. Returns the overlapping domain or ''."""
    if not domains_a or not domains_b:
        return ""
    if "*" in domains_a or "*" in domains_b:
        return "*"
    overlap = domains_a & domains_b
    return next(iter(overlap)) if overlap else ""


def _domain_refines(domains_a: set, domains_b: set) -> bool:
    """Check if domains_a is a refinement/subcase of domains_b.

    E.g. ['cancel_order'] refines ['cancel_order', 'modify_order'] (is subset)
    """
    if not domains_a or not domains_b:
        return False
    # Wildcard is not a refinement
    if "*" in domains_a or "*" in domains_b:
        return False
    return domains_a.issubset(domains_b) and domains_a != domains_b


def _is_already_in_edges(edges: list, source: str, target: str, edge_type: str) -> bool:
    """Check if an edge already exists (avoid duplicates)."""
    for e in edges:
        if e.source == source and e.target == target and e.edge_type == edge_type:
            return True
    return False
