"""V8: Execution Intelligence Layer — 执行智能层

AI 开始调度公司的全部执行资源。
支持优雅降级：模块缺失时降级为 None，不阻断启动。
"""
try:
    from execution.execution_queue import ExecutionQueue
except ImportError:
    ExecutionQueue = None

try:
    from execution.execution_agents import ExecutionEngine, SalesAgent, PricingAgent, CRMAgent, MarketingAgent, ContentAgent, FinanceAgent
except ImportError:
    ExecutionEngine = None
    SalesAgent = None
    PricingAgent = None
    CRMAgent = None
    MarketingAgent = None
    ContentAgent = None
    FinanceAgent = None

try:
    from execution.resource_scheduler import ResourceScheduler
except ImportError:
    ResourceScheduler = None

try:
    from execution.task_orchestrator import TaskOrchestrator
except ImportError:
    TaskOrchestrator = None

try:
    from execution.feedback_loop import FeedbackLoop
except ImportError:
    FeedbackLoop = None

try:
    from execution.kernel import ExecutionKernel, IdempotencyGuard, WorkerLoop, DeadLetterQueue
except ImportError:
    ExecutionKernel = None
    IdempotencyGuard = None
    WorkerLoop = None
    DeadLetterQueue = None
