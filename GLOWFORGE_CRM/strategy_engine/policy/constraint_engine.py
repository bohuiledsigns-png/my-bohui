"""Constraint Engine — 硬约束检查

在决策路由到 V2 之前执行最终约束检查，防止 V3 向 V2 发送违规指令。
"""
import logging

logger = logging.getLogger("constraint_engine")


class ConstraintEngine:
    """约束引擎 — 执行硬约束过滤器"""

    @staticmethod
    def check_constraints(strategy_report):
        """对策略报告执行完整约束检查

        返回:
            dict: { all_approved, approved_strategy, blocked_actions, modifications }
        """
        from strategy_engine.policy.business_policy import BusinessPolicy

        policy_result = BusinessPolicy.evaluate_strategy(strategy_report)
        blocked = []
        modifications = []

        # 硬违例 -> 阻止相关行动
        for v in policy_result.get("hard_violations", []):
            blocked.append({
                "action_type": v.get("policy_id", ""),
                "reason": v["detail"],
                "severity": "hard",
            })

        # 收集所有被阻止的行动
        all_blocked = ConstraintEngine._find_blocked_actions(strategy_report, policy_result)

        # 从策略报告中移除被阻止的部分
        approved = ConstraintEngine._filter_approved(strategy_report, all_blocked)

        return {
            "all_approved": len(all_blocked) == 0,
            "approved_strategy": approved,
            "blocked_actions": all_blocked,
            "modifications": modifications,
        }

    @staticmethod
    def _find_blocked_actions(report, policy_result):
        """找出所有被阻止的行动"""
        blocked = []
        for v in policy_result.get("hard_violations", []):
            blocked.append({
                "action": v.get("detail", "unknown"),
                "reason": v["rule"],
                "blocking_policy": v["policy_id"],
            })
        return blocked

    @staticmethod
    def _filter_approved(report, blocked):
        """从报告中移除被阻止的部分，返回仅获批的部分"""
        if not blocked:
            return report
        # 标记但保留结构（决策层决定是否忽略阻止）
        filtered = dict(report)
        filtered["constraint_warnings"] = [b["reason"] for b in blocked]
        return filtered

    @staticmethod
    def is_action_allowed(action_type, action_params):
        """检查单个行动是否允许"""
        from strategy_engine.policy.business_policy import BusinessPolicy

        for rule in BusinessPolicy.load_all():
            if rule["severity"] != "hard":
                continue
            check_type = rule["check_type"]
            if check_type == "country_allowed":
                country = action_params.get("country", "")
                if country and country not in rule["allowed_countries"]:
                    return False
            elif check_type == "max_discount":
                discount = action_params.get("discount", 0)
                if discount > rule["max_discount"]:
                    return False
        return True
