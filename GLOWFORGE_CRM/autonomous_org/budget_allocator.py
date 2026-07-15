"""BudgetAllocator — 动态预算分配器

动态百分比分配 + 每日按绩效再平衡。
写入 org_budget_allocations 表。
"""
import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger("glowforge.budget_allocator")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

MAX_ADJUSTMENT = 0.10  # 单次最大调整 10%


class BudgetAllocator:
    """动态预算分配器"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH
        self._total_budget = 100000.0  # 默认总预算，可被外部覆盖

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def set_total_budget(self, amount):
        """设置总预算基数"""
        self._total_budget = amount

    def calculate_allocation(self, period=None):
        """计算当前周期预算分配

        基于部门预算百分比 + 绩效调整。
        Returns:
            dict: {dept_id: {"amount": float, "pct": float, "performance": float}}
        """
        period = period or datetime.now().strftime("%Y-%m")
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT dept_id, budget_pct, performance FROM org_departments WHERE status='active'"
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                return {}

            total_pct = sum(r["budget_pct"] for r in rows)
            if total_pct <= 0:
                return {}

            # 按绩效加权调整
            total_perf = sum(r["performance"] for r in rows)
            allocations = {}
            for r in rows:
                base_pct = r["budget_pct"] / total_pct
                # 绩效加成: 高于平均绩效的部门获得更多预算
                if total_perf > 0 and len(rows) > 1:
                    avg_perf = total_perf / len(rows)
                    perf_factor = (r["performance"] - avg_perf) / avg_perf
                    adjustment = min(abs(perf_factor), MAX_ADJUSTMENT)
                    if perf_factor > 0:
                        adjusted_pct = base_pct * (1 + adjustment)
                    else:
                        adjusted_pct = base_pct * (1 - adjustment)
                else:
                    adjusted_pct = base_pct

                adjusted_pct = max(0.01, min(adjusted_pct, 0.50))  # 限制 1%–50%
                amount = self._total_budget * adjusted_pct
                allocations[r["dept_id"]] = {
                    "amount": round(amount, 2),
                    "pct": round(adjusted_pct, 4),
                    "performance": r["performance"],
                }

            # 归一化百分比总和为 100%
            total_adj = sum(a["pct"] for a in allocations.values())
            if total_adj > 0:
                for dept_id in allocations:
                    allocations[dept_id]["pct"] = round(
                        allocations[dept_id]["pct"] / total_adj, 4
                    )
                    allocations[dept_id]["amount"] = round(
                        self._total_budget * allocations[dept_id]["pct"], 2
                    )

            return allocations

        except Exception as e:
            logger.warning("[BudgetAllocator] calculate_allocation failed: %s", e)
            return {}

    def calculate_and_persist(self, period=None):
        """计算 + 持久化（一次性写入 'initial' 记录）"""
        alloc = self.calculate_allocation(period)
        if alloc:
            self._persist_allocation(period, alloc)
        return alloc

    def rebalance(self, period=None):
        """每日再平衡: 计算新分配并记录变化

        Returns:
            dict: 包含前后对比的分配结果
        """
        period = period or datetime.now().strftime("%Y-%m")

        # 计算新分配（不持久化 — calculate_allocation 已去掉 persist）
        new_alloc = self.calculate_allocation(period)

        # 获取当前分配作为 baseline
        prev = self._get_current_allocation(period)
        prev_pcts = {r["dept_id"]: r["pct"] for r in prev} if prev else {}

        # 单次持久化（带 previous_pct 和 reason）
        try:
            conn = self._get_conn()
            try:
                for dept_id, alloc in new_alloc.items():
                    prev_pct = prev_pcts.get(dept_id, alloc["pct"])
                    conn.execute(
                        """INSERT INTO org_budget_allocations
                           (period, dept_id, amount, pct, previous_pct, reason)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (period, dept_id, alloc["amount"], alloc["pct"],
                         prev_pct, "performance_rebalance"),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[BudgetAllocator] rebalance persist failed: %s", e)

        return {
            "period": period,
            "previous": prev_pcts,
            "allocations": new_alloc,
        }

    def _get_current_allocation(self, period):
        """获取当前周期已持久化的分配"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM org_budget_allocations WHERE period=? ORDER BY id",
                    (period,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception:
            return []

    def _persist_allocation(self, period, allocations):
        """持久化预算分配（仅 calculate_and_persist 调用）"""
        try:
            conn = self._get_conn()
            try:
                for dept_id, alloc in allocations.items():
                    conn.execute(
                        """INSERT INTO org_budget_allocations
                           (period, dept_id, amount, pct, reason)
                           VALUES (?, ?, ?, ?, ?)""",
                        (period, dept_id, alloc["amount"], alloc["pct"], "initial"),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[BudgetAllocator] persist failed: %s", e)

    def get_allocation_history(self, dept_id=None, limit=20):
        """获取分配历史"""
        try:
            conn = self._get_conn()
            try:
                if dept_id:
                    rows = conn.execute(
                        "SELECT * FROM org_budget_allocations WHERE dept_id=? ORDER BY id DESC LIMIT ?",
                        (dept_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM org_budget_allocations ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[BudgetAllocator] get_allocation_history failed: %s", e)
            return []
