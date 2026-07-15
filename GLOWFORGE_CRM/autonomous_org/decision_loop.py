"""AutonomousDecisionLoop — 自治决策循环守护线程

7 步循环:
Sense Market → Analyze Graph → Board Decision → Budget Allocate
→ Dept Dispatch → Feedback → Evolution
"""
import logging
import threading
import time

logger = logging.getLogger("glowforge.decision_loop")

INTERVAL = 600  # 10 分钟默认


class AutonomousDecisionLoop:
    """7 步自治决策循环"""

    def __init__(self, board, dept_system, budget_alloc, protocol, interval=INTERVAL):
        self._board = board
        self._dept_system = dept_system
        self._budget_alloc = budget_alloc
        self._protocol = protocol
        self._interval = interval
        self._thread = None
        self._running = False
        self._cycle_count = 0
        self._last_board_session = None

    def run_loop(self):
        """主循环：7 步自治决策"""
        logger.info("[DecisionLoop] Started (interval=%ds)", self._interval)
        while self._running:
            try:
                self._cycle()
                self._cycle_count += 1
            except Exception as e:
                logger.error("[DecisionLoop] Cycle error: %s", e)
            time.sleep(self._interval)

    def _cycle(self):
        """执行一轮 7 步决策"""
        context = {"cycle": self._cycle_count}

        # Step 1: Sense Market — 感知市场
        # （预留：从外部数据源读取市场信号，当前传递 cycle 上下文）

        if self._cycle_count % 6 == 0:
            # Step 2-3: Analyze Graph → Board Decision（每 6 轮=60分钟一次董事会）
            self._step_board_session(context)
        else:
            logger.debug("[DecisionLoop] Cycle %d: skip board (every 6th)", self._cycle_count)

        # Step 4: Budget Allocate（每轮检查，但只在需要时分配）
        self._step_budget_allocate(context)

        # Step 5: Dept Dispatch — 部门派发（预留）
        self._step_dept_dispatch(context)

        # Step 6-7: Feedback → Evolution（日志记录）
        if self._cycle_count % 6 == 0 and self._last_board_session:
            self._step_feedback(context)

    def _step_board_session(self, context):
        """Step 2-3: 董事会分析 + 决策"""
        try:
            if self._board:
                self._last_board_session = self._board.board_session(context)
                count = self._last_board_session.get("decision_count", 0)
                logger.info("[DecisionLoop] Board session: %d decisions", count)
        except Exception as e:
            logger.warning("[DecisionLoop] Board session failed: %s", e)

    def _step_budget_allocate(self, context):
        """Step 4: 预算分配"""
        try:
            if self._budget_alloc:
                alloc = self._budget_alloc.calculate_allocation()
                if alloc:
                    logger.debug("[DecisionLoop] Budget allocation: %d depts", len(alloc))
        except Exception as e:
            logger.warning("[DecisionLoop] Budget allocation failed: %s", e)

    def _step_dept_dispatch(self, context):
        """Step 5: 部门派发（预留集成点）

        可根据董事会决议向各部门派发执行任务。
        """
        if not self._protocol or not self._last_board_session:
            return

        # 按决策类型分派到对应部门
        board_decisions = self._last_board_session.get("board_decisions", [])
        for decision in board_decisions:
            agent = decision.get("agent", "")
            dept_map = {"CEO": "operations", "CFO": "finance",
                        "CMO": "marketing", "COO": "operations"}
            target_dept = dept_map.get(agent)
            if target_dept:
                logger.debug(
                    "[DecisionLoop] Dispatch %s decision to %s", agent, target_dept
                )

    def _step_feedback(self, context):
        """Step 6-7: 反馈 + 进化

        评估上次董事会决策的 ROI 和执行状态。
        """
        try:
            session_id = self._last_board_session.get("session_id", "")
            if self._board and session_id:
                decisions = self._board.get_session_decisions(session_id)
                logger.info(
                    "[DecisionLoop] Feedback: session %s has %d decisions recorded",
                    session_id, len(decisions),
                )
        except Exception as e:
            logger.warning("[DecisionLoop] Feedback step failed: %s", e)

    def start(self):
        """启动守护线程"""
        if self._thread and self._thread.is_alive():
            logger.warning("[DecisionLoop] Already running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self.run_loop, daemon=True, name="AutonomousDecisionLoop"
        )
        self._thread.start()
        logger.info("[DecisionLoop] Daemon thread started")

    def stop(self):
        """停止守护线程"""
        self._running = False
        logger.info("[DecisionLoop] Stopped")
