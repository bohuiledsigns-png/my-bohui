"""Agent Manager — Agent调度与客户分配管理

功能：
  1. 每天自动调度哪个Agent负责哪个客户
  2. A类客户=Closer主导，B类=Consultant主导，C类=Hunter激活
  3. 与V4 scheduler集成，将Agent分配到不同时段
"""

import sys
import os
import json
from datetime import datetime, date
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from database import get_db


class AgentManager:
    """Agent调度管理器"""

    # Agent调度时段
    SCHEDULE_SLOTS = {
        "09:00": {"agents": ["closer_agent", "hunter_agent"], "target": "A", "action": "push_close"},
        "12:00": {"agents": ["consultant_agent", "soft_seller_agent"], "target": "B", "action": "case_study"},
        "14:00": {"agents": ["technical_agent", "consultant_agent"], "target": "B", "action": "technical_followup"},
        "18:00": {"agents": ["hunter_agent", "soft_seller_agent"], "target": "C", "action": "wake_up"},
        "22:00": {"agents": ["closer_agent"], "target": "A", "action": "final_close"},
    }

    # 优先级 → 主导Agent映射
    PRIORITY_LEAD_AGENT = {
        "A": "closer_agent",
        "B": "consultant_agent",
        "C": "hunter_agent",
    }

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        """确保表存在"""
        pass

    def get_customers_for_slot(self, slot_time: str) -> list:
        """获取指定时段应该处理的客户列表

        Args:
            slot_time: "09:00", "12:00", "14:00", "18:00", "22:00"

        Returns:
            list: [{customer_id, name, priority_class, state, ...}]
        """
        slot_config = self.SCHEDULE_SLOTS.get(slot_time, {})
        target_priority = slot_config.get("target", "C")
        agents = slot_config.get("agents", [])

        try:
            conn = get_db()
            # 获取符合条件的客户
            rows = conn.execute(
                """SELECT c.id, c.name, c.country,
                          COALESCE(v.priority_class, 'C') as priority_class,
                          COALESCE(v.priority_score, 0) as score,
                          COALESCE(v.priority_action, '') as action,
                          COALESCE(v2.final_state, 'NEW') as state
                   FROM customers c
                   LEFT JOIN v4_customer_state v ON c.id = v.customer_id
                   LEFT JOIN (
                       SELECT customer_id, final_state
                       FROM v3_conversions
                       WHERE final_result='open'
                       ORDER BY id DESC
                   ) v2 ON c.id = v2.customer_id
                   WHERE c.status != 'customer'
                   ORDER BY
                     CASE WHEN v.priority_class = ? THEN 0 ELSE 1 END,
                     v.priority_score DESC
                   LIMIT 30""",
                (target_priority,)
            ).fetchall()
            conn.close()

            results = []
            for r in rows:
                customer_id = r["id"]
                # 确定该客户应该用哪个Agent
                assigned_agent = self.assign_agent_for_customer(
                    customer_id,
                    priority=r["priority_class"],
                    state=r["state"],
                    agents_pool=agents,
                )
                results.append({
                    "customer_id": customer_id,
                    "name": r["name"] or f"#{customer_id}",
                    "country": r["country"] or "",
                    "priority_class": r["priority_class"],
                    "score": r["score"],
                    "state": r["state"],
                    "assigned_agent": assigned_agent,
                    "suggested_action": slot_config.get("action", "followup"),
                })

            return results
        except Exception:
            return []

    def assign_agent_for_customer(self, customer_id: int, priority: str = "C",
                                   state: str = "NEW", agents_pool: list = None) -> str:
        """为特定客户分配最适合的Agent

        Args:
            customer_id: 客户ID
            priority: A/B/C
            state: NEW/BUDGET/OBJECTION/FINAL
            agents_pool: 可用的Agent池

        Returns:
            str: agent_id
        """
        if agents_pool is None:
            agents_pool = list(self.PRIORITY_LEAD_AGENT.values())

        # 从WinnerSelector获取学习数据调整
        try:
            from .winner_selector import WinnerSelector
            adjusted_weights = WinnerSelector().get_adjusted_weights(state, priority)
        except Exception:
            adjusted_weights = {}

        # 根据状态调整
        state_preference = {
            "NEW": "consultant_agent",
            "NEEDS_ANALYSIS": "consultant_agent",
            "BUDGET": "hunter_agent",
            "OBJECTION": "hunter_agent",
            "FINAL": "closer_agent",
        }

        preferred = state_preference.get(state, "consultant_agent")
        if preferred in agents_pool:
            return preferred

        # 按优先级主导
        lead = self.PRIORITY_LEAD_AGENT.get(priority, "consultant_agent")
        if lead in agents_pool:
            return lead

        # 默认返回池中第一个
        return agents_pool[0] if agents_pool else "consultant_agent"

    def get_daily_schedule(self, target_date: str = None) -> dict:
        """获取某天的Agent调度计划

        Args:
            target_date: "YYYY-MM-DD"，默认今天

        Returns:
            dict: {slot_time: {agents, target, customers: [...]}}
        """
        if target_date is None:
            target_date = date.today().isoformat()

        schedule = {}
        for slot_time, config in self.SCHEDULE_SLOTS.items():
            customers = self.get_customers_for_slot(slot_time)
            schedule[slot_time] = {
                "agents": config["agents"],
                "target_priority": config["target"],
                "suggested_action": config["action"],
                "customer_count": len(customers),
                "customers": customers[:10],  # 限制返回数量
            }

        return {
            "date": target_date,
            "total_slots": len(self.SCHEDULE_SLOTS),
            "total_customers": sum(s["customer_count"] for s in schedule.values()),
            "schedule": schedule,
        }

    def get_agent_load(self) -> list:
        """获取各Agent当前负载

        Returns:
            list: [{agent_id, name, assigned_count, strategy}]
        """
        agent_info = {
            "hunter_agent": "Hunter (Alex)",
            "consultant_agent": "Consultant (Sarah)",
            "soft_seller_agent": "Soft Seller (Emma)",
            "technical_agent": "Technical (Mike)",
            "closer_agent": "Closer (Diana)",
        }

        try:
            conn = get_db()
            results = []
            for agent_id, agent_name in agent_info.items():
                row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM customers
                       WHERE assigned_agent=? AND status != 'customer'""",
                    (agent_id,)
                ).fetchone()
                results.append({
                    "agent_id": agent_id,
                    "name": agent_name,
                    "assigned_count": row["cnt"] if row else 0,
                })
            conn.close()
            return results
        except Exception:
            return [{"agent_id": k, "name": v, "assigned_count": 0} for k, v in agent_info.items()]


# 快捷入口
manager = AgentManager()


def get_daily_schedule(target_date: str = None) -> dict:
    return manager.get_daily_schedule(target_date)


def get_customers_for_slot(slot_time: str) -> list:
    return manager.get_customers_for_slot(slot_time)
