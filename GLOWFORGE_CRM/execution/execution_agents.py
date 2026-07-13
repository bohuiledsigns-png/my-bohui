"""Execution Agents — Agent 执行层

BaseAgent 抽象基类 + 6 个具体 Agent + ExecutionEngine 守护线程。
每个 Agent 从 ExecutionQueue 出队后执行具体业务逻辑。
"""
import logging
import threading
import time
from abc import ABC, abstractmethod

logger = logging.getLogger("glowforge.execution_agents")


class BaseAgent(ABC):
    """Agent 执行基类"""

    def __init__(self, agent_id, queue_ref, capabilities=None):
        self.agent_id = agent_id
        self._queue = queue_ref
        self._capabilities = set(capabilities or [])
        self.active_tasks = 0
        self.total_executed = 0

    def can_handle(self, task_type):
        """Check if this agent can handle a given task type."""
        return task_type in self._capabilities

    @abstractmethod
    def execute(self, task):
        """Execute a task. Must be implemented by subclasses.

        Args:
            task: dict from execution_queue row (includes task_type, payload_json, etc.)

        Returns:
            dict with execution result
        """
        raise NotImplementedError

    def _pre_exec_check(self, task):
        """V7 Firewall re-check before execution."""
        if self._queue:
            return self._queue.recheck_firewall(task["id"])
        return "ALLOW"


class SalesAgent(BaseAgent):
    """Sales Agent — 销售执行: 发消息、报价、谈判、跟进"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "send_message", "send_quote", "negotiate", "followup",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")

        self.active_tasks += 1
        try:
            if task_type == "send_message" or task_type == "followup":
                content = payload.get("content", "")
                logger.info("[SalesAgent] Sending message to customer %s: %.50s",
                            customer_id, content)
                result = {"sent": True, "content_preview": content[:100]}
            elif task_type == "send_quote":
                logger.info("[SalesAgent] Sending quote to customer %s", customer_id)
                result = {"quote_sent": True}
            elif task_type == "negotiate":
                logger.info("[SalesAgent] Negotiating with customer %s", customer_id)
                result = {"negotiated": True}
            else:
                result = {"executed": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class MarketingAgent(BaseAgent):
    """Marketing Agent — 营销执行: 发目录、群发、活动"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "send_catalog", "broadcast", "campaign",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")
        self.active_tasks += 1
        try:
            logger.info("[MarketingAgent] %s to customer %s", task_type, customer_id)
            result = {"executed": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class PricingAgent(BaseAgent):
    """Pricing Agent — 定价执行: 计算报价、调折扣、检查价格"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "calculate_price", "adjust_discount", "price_check",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")
        self.active_tasks += 1
        try:
            logger.info("[PricingAgent] %s for customer %s", task_type, customer_id)
            result = {"calculated": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class CRMAgent(BaseAgent):
    """CRM Agent — CRM 操作: 更新线索、创建任务、打标签"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "update_lead", "create_task", "tag_customer",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")
        self.active_tasks += 1
        try:
            logger.info("[CRMAgent] %s for customer %s", task_type, customer_id)
            result = {"updated": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class ContentAgent(BaseAgent):
    """Content Agent — 内容生成: 写文案、翻译、校对"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "generate_content", "translate", "proofread",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")
        self.active_tasks += 1
        try:
            logger.info("[ContentAgent] %s for customer %s", task_type, customer_id)
            result = {"generated": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class FinanceAgent(BaseAgent):
    """Finance Agent — 财务操作 (预留)"""

    def __init__(self, agent_id, queue_ref):
        super().__init__(agent_id, queue_ref, capabilities=[
            "create_invoice", "check_credit", "payment_reminder",
        ])

    def execute(self, task):
        payload = self._parse_payload(task)
        task_type = task["task_type"]
        customer_id = payload.get("customer_id", "?")
        self.active_tasks += 1
        try:
            logger.info("[FinanceAgent] %s for customer %s (reserved)", task_type, customer_id)
            result = {"executed": True, "reserved": True}
            self.total_executed += 1
            return result
        finally:
            self.active_tasks -= 1

    def _parse_payload(self, task):
        import json
        try:
            return json.loads(task.get("payload_json", "{}"))
        except Exception:
            return {}


class ExecutionEngine:
    """Execution Engine 守护线程: 出队 → 匹配 Agent → 执行 → 完成/失败"""

    def __init__(self, queue, agents, interval=15):
        self._queue = queue
        self._agents = agents
        self._interval = interval
        self._thread = None
        self._running = False

    def run_loop(self):
        """主循环: 定期轮询队列并派发任务"""
        logger.info("[ExecutionEngine] Started (interval=%ds)", self._interval)
        while self._running:
            try:
                tasks = self._queue.dequeue("execution_engine", batch_size=5)
                for task in tasks:
                    agent = self._match_agent(task)
                    if agent:
                        # V7 Firewall 执行前检查
                        recheck = self._queue.recheck_firewall(task["id"])
                        if recheck == "BLOCK":
                            logger.warning(
                                "[ExecutionEngine] Task %d blocked by V7 at exec time",
                                task["id"],
                            )
                            continue
                        try:
                            result = agent.execute(task)
                            self._queue.complete(task["id"], result)
                            logger.debug(
                                "[ExecutionEngine] Task %d completed by %s",
                                task["id"], agent.agent_id,
                            )
                        except Exception as e:
                            logger.error(
                                "[ExecutionEngine] Task %d failed: %s",
                                task["id"], e,
                            )
                            self._queue.fail(task["id"], str(e))
                    else:
                        logger.warning(
                            "[ExecutionEngine] No agent for task %d type=%s",
                            task["id"], task["task_type"],
                        )
                        self._queue.fail(task["id"], "No suitable agent found")

                # Clean stale locks periodically
                self._queue.cleanup_stale_locks(timeout=300)
            except Exception as e:
                logger.error("[ExecutionEngine] Loop error: %s", e)
            time.sleep(self._interval)

    def _match_agent(self, task):
        """按 task_type + 负载最低匹配 Agent"""
        task_type = task.get("task_type", "")
        suitable = [a for a in self._agents if a.can_handle(task_type)]
        if not suitable:
            return None
        return min(suitable, key=lambda a: a.active_tasks)

    def start(self):
        """启动守护线程"""
        if self._thread and self._thread.is_alive():
            logger.warning("[ExecutionEngine] Already running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self.run_loop, daemon=True, name="ExecutionEngine"
        )
        self._thread.start()
        logger.info("[ExecutionEngine] Daemon thread started")

    def stop(self):
        """停止守护线程"""
        self._running = False
        logger.info("[ExecutionEngine] Stopped")
