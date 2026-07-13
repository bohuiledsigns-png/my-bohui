"""InterDeptProtocol — 部门间协作协议

标准化部门通信路由：sales↔marketing, marketing↔finance,
finance↔operations, operations↔production, customer_success↔sales。
"""
import json
import logging

logger = logging.getLogger("glowforge.inter_dept_protocol")

# 从 config.py 读取协作路由（单数据源）
try:
    from autonomous_org.config import COLLABORATION_ROUTES
except ImportError:
    COLLABORATION_ROUTES = {}

# 动作处理映射（轻量级规则引擎）
ACTION_HANDLERS = {}


def _register_default_handlers():
    """注册默认协作动作处理器"""
    if ACTION_HANDLERS:
        return

    # sales → marketing: request_leads
    ACTION_HANDLERS[("sales", "marketing", "request_leads")] = (
        lambda ctx: {"status": "ok", "message": "Leads requested", "leads_count": 5}
    )
    ACTION_HANDLERS[("sales", "marketing", "share_campaign_feedback")] = (
        lambda ctx: {"status": "ok", "message": "Feedback shared"}
    )

    # marketing → sales: send_leads
    ACTION_HANDLERS[("marketing", "sales", "send_leads")] = (
        lambda ctx: {"status": "ok", "message": "Leads sent", "leads": []}
    )
    ACTION_HANDLERS[("marketing", "sales", "campaign_results")] = (
        lambda ctx: {"status": "ok", "message": "Campaign results delivered"}
    )

    # marketing → finance: request_budget
    ACTION_HANDLERS[("marketing", "finance", "request_budget")] = (
        lambda ctx: {"status": "ok", "message": "Budget requested", "amount": ctx.get("amount", 0)}
    )
    ACTION_HANDLERS[("marketing", "finance", "report_roi")] = (
        lambda ctx: {"status": "ok", "message": "ROI reported"}
    )

    # finance → operations: approve_budget
    ACTION_HANDLERS[("finance", "operations", "approve_budget")] = (
        lambda ctx: {"status": "approved" if ctx.get("amount", 0) < 50000 else "pending",
                     "message": "Budget " + ("approved" if ctx.get("amount", 0) < 50000 else "needs review")}
    )
    ACTION_HANDLERS[("finance", "operations", "report_spend")] = (
        lambda ctx: {"status": "ok", "message": "Spend reported"}
    )

    # operations → production: dispatch_tasks
    ACTION_HANDLERS[("operations", "production", "dispatch_tasks")] = (
        lambda ctx: {"status": "ok", "message": "Tasks dispatched", "task_count": len(ctx.get("tasks", []))}
    )
    ACTION_HANDLERS[("operations", "production", "capacity_check")] = (
        lambda ctx: {"status": "ok", "message": "Capacity checked", "available": True}
    )

    # production → customer_success: quality_alert
    ACTION_HANDLERS[("production", "customer_success", "quality_alert")] = (
        lambda ctx: {"status": "ok", "message": "Quality alert sent"}
    )
    ACTION_HANDLERS[("production", "customer_success", "delivery_update")] = (
        lambda ctx: {"status": "ok", "message": "Delivery updated"}
    )

    # customer_success → sales: upsell_opportunity
    ACTION_HANDLERS[("customer_success", "sales", "upsell_opportunity")] = (
        lambda ctx: {"status": "ok", "message": "Upsell opportunity forwarded"}
    )
    ACTION_HANDLERS[("customer_success", "sales", "churn_warning")] = (
        lambda ctx: {"status": "ok", "message": "Churn warning sent"}
    )


_register_default_handlers()


class InterDeptProtocol:
    """部门间协作协议"""

    def __init__(self):
        pass

    def get_routes(self, from_dept=None, to_dept=None):
        """获取可用协作路由

        Args:
            from_dept: 可选，源部门
            to_dept: 可选，目标部门

        Returns:
            list of (from_dept, to_dept, actions)
        """
        routes = []
        for (f, t), actions in COLLABORATION_ROUTES.items():
            if from_dept and f != from_dept:
                continue
            if to_dept and t != to_dept:
                continue
            routes.append({"from": f, "to": t, "actions": actions})
        return routes

    def department_collaborate(self, from_dept, to_dept, action, context=None):
        """执行部门间协作

        Args:
            from_dept: 发起部门
            to_dept: 目标部门
            action: 协作动作类型
            context: dict, 附加上下文

        Returns:
            dict: 协作结果
        """
        context = context or {}

        # 检查路由是否存在
        allowed = COLLABORATION_ROUTES.get((from_dept, to_dept), [])
        if action not in allowed:
            logger.warning(
                "[InterDept] Invalid route: %s→%s action=%s", from_dept, to_dept, action
            )
            return {
                "status": "error",
                "error": "route_not_allowed",
                "message": f"'{from_dept}→{to_dept}' 不允许 '{action}' 动作",
            }

        # 查找处理器并执行
        handler = ACTION_HANDLERS.get((from_dept, to_dept, action))
        if handler:
            try:
                result = handler(context)
                logger.info(
                    "[InterDept] %s→%s %s → %s",
                    from_dept, to_dept, action, result.get("status"),
                )
                result.update({"from": from_dept, "to": to_dept, "action": action})
                return result
            except Exception as e:
                logger.warning("[InterDept] handler failed: %s", e)
                return {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "from": from_dept,
            "to": to_dept,
            "action": action,
            "message": f"No handler for {action}, but route exists",
        }

    def broadcast(self, from_dept, message, to_depts=None):
        """部门广播: 从源部门向指定部门（或全部）发送消息

        Args:
            from_dept: 源部门
            message: 消息内容
            to_depts: 目标部门列表，None 表示所有可能的部门

        Returns:
            list of 各目标部门的响应
        """
        results = []
        all_depts = set()
        for (f, t) in COLLABORATION_ROUTES:
            if f == from_dept:
                all_depts.add(t)
        targets = to_depts or list(all_depts)

        for target in targets:
            results.append({
                "from": from_dept,
                "to": target,
                "message": message,
                "status": "delivered",
            })

        return results
