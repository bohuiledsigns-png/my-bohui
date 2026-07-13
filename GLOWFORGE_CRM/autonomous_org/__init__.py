"""V9: Autonomous Business Organization — 自治组织系统

把你的 CRM + AI 系统从"工具集合"升级为"AI 公司组织结构本身"。
支持优雅降级：模块缺失时降级为 None，不阻断启动。
"""
import logging

logger = logging.getLogger("glowforge.autonomous_org")

try:
    from autonomous_org.virtual_board import VirtualBoard
except ImportError:
    VirtualBoard = None
    logger.debug("VirtualBoard not available")

try:
    from autonomous_org.department_system import DepartmentSystem
except ImportError:
    DepartmentSystem = None
    logger.debug("DepartmentSystem not available")

try:
    from autonomous_org.budget_allocator import BudgetAllocator
except ImportError:
    BudgetAllocator = None
    logger.debug("BudgetAllocator not available")

try:
    from autonomous_org.inter_dept_protocol import InterDeptProtocol
except ImportError:
    InterDeptProtocol = None
    logger.debug("InterDeptProtocol not available")

try:
    from autonomous_org.decision_loop import AutonomousDecisionLoop
except ImportError:
    AutonomousDecisionLoop = None
    logger.debug("AutonomousDecisionLoop not available")


def start_autonomous_org():
    """启动自治组织系统的统一入口。

    按依赖顺序初始化所有模块，返回 (board, dept_system, budget_alloc, protocol, loop) 元组。
    任意模块失败不影响其他模块。
    """
    board = None
    dept_system_obj = None
    budget_alloc = None
    protocol = None
    loop = None

    if VirtualBoard is not None:
        try:
            board = VirtualBoard()
            logger.info("[V9] VirtualBoard initialized")
        except Exception as e:
            logger.warning("[V9] VirtualBoard init failed (graceful): %s", e)

    if DepartmentSystem is not None:
        try:
            dept_system_obj = DepartmentSystem()
            count = dept_system_obj.initialize()
            logger.info("[V9] DepartmentSystem initialized with %d depts", count)
        except Exception as e:
            logger.warning("[V9] DepartmentSystem init failed (graceful): %s", e)

    if BudgetAllocator is not None:
        try:
            budget_alloc = BudgetAllocator()
            logger.info("[V9] BudgetAllocator initialized")
        except Exception as e:
            logger.warning("[V9] BudgetAllocator init failed (graceful): %s", e)

    if InterDeptProtocol is not None:
        try:
            protocol = InterDeptProtocol()
            logger.info("[V9] InterDeptProtocol initialized")
        except Exception as e:
            logger.warning("[V9] InterDeptProtocol init failed (graceful): %s", e)

    if AutonomousDecisionLoop is not None:
        try:
            loop = AutonomousDecisionLoop(board, dept_system_obj, budget_alloc, protocol)
            # loop.start()  — 停掉 10 分钟一轮的董事会循环，数据无人读
            logger.info("[V9] AutonomousDecisionLoop created (daemon disabled — no consumers)")
        except Exception as e:
            logger.warning("[V9] AutonomousDecisionLoop init failed (graceful): %s", e)

    return board, dept_system_obj, budget_alloc, protocol, loop
