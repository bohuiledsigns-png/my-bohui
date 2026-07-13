"""V0-SAFETY: System Safety Convergence Layer + Control Plane

安全能力集中到此包，可观测、可告警、可回溯。
"""

# Graceful degradation imports — 模块缺失时降级为 None，不阻断启动
try:
    from safety.state_registry import StateRegistry
except ImportError:
    StateRegistry = None

try:
    from safety.execution_firewall import ExecutionFirewall
except ImportError:
    ExecutionFirewall = None

try:
    from safety.agent_coordinator import AgentCoordinator
except ImportError:
    AgentCoordinator = None

try:
    from safety.policy_engine import PolicyEngine
except ImportError:
    PolicyEngine = None

try:
    from safety.risk_engine import RiskEngine
except ImportError:
    RiskEngine = None

try:
    from safety.graph_check import GraphCheck
except ImportError:
    GraphCheck = None

try:
    from safety.audit_logger import AuditLogger
except ImportError:
    AuditLogger = None

try:
    from safety.unified_escalation_engine import UnifiedEscalationEngine, start_uee_scanner, stop_uee_scanner
except ImportError:
    UnifiedEscalationEngine = None
    start_uee_scanner = None
    stop_uee_scanner = None

try:
    from safety.business_execution_gate import BusinessPolicyGate
except ImportError:
    BusinessPolicyGate = None

try:
    from safety.constraint_set import ConstraintSet, Constraint
except ImportError:
    ConstraintSet = None
    Constraint = None

try:
    from safety.constraint_graph import PolicyGraph, PolicyEdge
except ImportError:
    PolicyGraph = None
    PolicyEdge = None

try:
    from safety.constraint_causal_memory import ConstraintCausalMemory
except ImportError:
    ConstraintCausalMemory = None

try:
    from safety.constraint_query import ConstraintQueryEngine
except ImportError:
    ConstraintQueryEngine = None
