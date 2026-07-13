"""TaskOrchestrator — 目标分解引擎

把业务目标拆成可执行任务链。
主路径: 调 ask_ali AI 分解 | 回退: 规则模板。
"""
import json
import logging
import uuid

logger = logging.getLogger("glowforge.task_orchestrator")

# 预定义目标模板 (AI 不可用时回退)
GOAL_TEMPLATES = {
    "follow_up_quote": [
        {"task_type": "send_message", "priority": 5,
         "label": "发送跟进提醒"},
        {"task_type": "followup", "priority": 5,
         "label": "检查报价状态"},
        {"task_type": "update_lead", "priority": 8,
         "label": "更新CRM线索状态"},
    ],
    "new_lead_welcome": [
        {"task_type": "send_message", "priority": 3,
         "label": "发送欢迎介绍"},
        {"task_type": "send_catalog", "priority": 5,
         "label": "发送产品目录"},
        {"task_type": "tag_customer", "priority": 8,
         "label": "客户打标签"},
    ],
    "price_negotiation": [
        {"task_type": "price_check", "priority": 3,
         "label": "检查利润率底线"},
        {"task_type": "adjust_discount", "priority": 4,
         "label": "计算折扣空间"},
        {"task_type": "send_message", "priority": 5,
         "label": "发送报价方案"},
        {"task_type": "update_lead", "priority": 8,
         "label": "更新谈判状态"},
    ],
    "order_confirmation": [
        {"task_type": "price_check", "priority": 3,
         "label": "核实订单金额"},
        {"task_type": "send_message", "priority": 4,
         "label": "发送确认通知"},
        {"task_type": "tag_customer", "priority": 7,
         "label": "标记为已成交客户"},
        {"task_type": "update_lead", "priority": 8,
         "label": "更新CRM为成交"},
    ],
    "reengagement": [
        {"task_type": "send_message", "priority": 4,
         "label": "发送重新激活消息"},
        {"task_type": "followup", "priority": 6,
         "label": "跟踪回复情况"},
        {"task_type": "update_lead", "priority": 8,
         "label": "更新冷淡状态"},
    ],
}


class TaskOrchestrator:
    """目标分解引擎"""

    def __init__(self, queue_ref=None):
        self._queue = queue_ref

    def decompose_goal(self, goal, customer_id, context=None):
        """分解目标为任务链.

        Args:
            goal: dict with 'type' and optional 'description'
                  e.g. {"type": "follow_up_quote", "description": "跟进报价客户"}
            customer_id: int
            context: optional dict with additional context

        Returns:
            list of task dicts ready for enqueue
        """
        goal_type = goal.get("type", "unknown")
        description = goal.get("description", "")

        # 主路径: AI 分解 (预留 ask_ali 接口)
        tasks = self._ai_decompose(goal_type, description, customer_id, context)
        if tasks:
            return tasks

        # 回退: 规则模板
        tasks = self._rule_based_decompose(goal_type, customer_id, context)
        if tasks:
            return tasks

        # 终极回退: 单任务
        return [self._make_task("send_message", customer_id, priority=5)]

    def submit_tasks(self, tasks):
        """批量入队到 ExecutionQueue.

        Args:
            tasks: list of task dicts

        Returns:
            list of queue_ids (None for failed enqueues)
        """
        if not self._queue:
            logger.warning("[TaskOrchestrator] No queue reference, cannot submit")
            return []
        ids = []
        for task in tasks:
            qid = self._queue.enqueue(
                task_type=task["task_type"],
                payload=task.get("payload", {}),
                priority=task.get("priority", 5),
                source_agent="task_orchestrator",
            )
            ids.append(qid)
        logger.info("[TaskOrchestrator] Submitted %d tasks, %d enqueued",
                     len(tasks), sum(1 for i in ids if i is not None))
        return ids

    def _ai_decompose(self, goal_type, description, customer_id, context):
        """AI 分解 — 预留 ask_ali 接口"""
        # TODO: 集成 ask_ali 实现 AI 驱动分解
        return None

    def _rule_based_decompose(self, goal_type, customer_id, context):
        """规则模板回退"""
        template = GOAL_TEMPLATES.get(goal_type)
        if not template:
            return None
        tasks = []
        for step in template:
            payload = {
                "customer_id": customer_id,
                "task_label": step["label"],
                "goal_type": goal_type,
            }
            if context:
                payload.update(context)
            tasks.append(self._make_task(
                step["task_type"], customer_id,
                priority=step["priority"],
                payload=payload,
            ))
        return tasks

    def _make_task(self, task_type, customer_id, priority=5, payload=None):
        """构造标准任务 dict"""
        base = {
            "task_type": task_type,
            "priority": priority,
            "payload": dict(payload or {}),
            "payload": {
                "customer_id": customer_id,
                **(payload or {}),
            },
        }
        return base
