"""FeedbackLoop — 反馈闭环

记录执行结果、推导利润影响、关闭目标、失败模式分析。
"""
import json
import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger("glowforge.feedback_loop")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class FeedbackLoop:
    """执行反馈闭环"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def record_result(self, task_id, outcome, goal_id="", customer_id=None,
                      profit_impact=0.0, feedback=None, error_category=""):
        """记录任务执行结果到 execution_feedback 表。

        Args:
            task_id: execution_queue id
            outcome: 'success' | 'partial' | 'failure' | 'cancelled'
            goal_id: execution_tasks.goal_id (if applicable)
            customer_id: int
            profit_impact: derived profit impact
            feedback: dict with detailed feedback data
            error_category: failure classification string
        """
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO execution_feedback
                   (task_id, goal_id, customer_id, outcome, profit_impact,
                    feedback_json, error_category)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (task_id, goal_id, customer_id,
                 outcome, profit_impact,
                 json.dumps(feedback or {}, ensure_ascii=False),
                 error_category),
            )
            conn.commit()
            conn.close()
            logger.debug("[FeedbackLoop] Recorded outcome=%s for task %s", outcome, task_id)
            return True
        except Exception as e:
            logger.warning("[FeedbackLoop] record_result failed: %s", e)
            return False

    def derive_profit_impact(self, task_id):
        """从关联订单/报价推导利润影响（预留）"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM execution_queue WHERE id=?", (task_id,)
            ).fetchone()
            conn.close()
            if not row:
                return 0.0
            payload = json.loads(row["payload_json"] or "{}")
            price = payload.get("price") or payload.get("total_amount") or 0
            # 简单估算: 利润影响 = 价格的 30%
            impact = float(price) * 0.3
            return round(impact, 2)
        except Exception:
            return 0.0

    def close_goal(self, goal_id):
        """检查目标所有子任务是否已完成/失败，关闭目标。

        Returns:
            'completed' | 'partial' | 'failed' | 'active'
        """
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT status FROM execution_tasks WHERE goal_id=?",
                (goal_id,),
            ).fetchall()
            conn.close()
            if not rows:
                return "active"
            statuses = [r["status"] for r in rows]
            if all(s == "completed" for s in statuses):
                return "completed"
            if all(s in ("completed", "failed", "cancelled") for s in statuses):
                return "partial"
            if all(s in ("failed", "cancelled") for s in statuses):
                return "failed"
            return "active"
        except Exception as e:
            logger.warning("[FeedbackLoop] close_goal failed: %s", e)
            return "active"

    def _analyze_failure(self, task_id, error):
        """失败模式分类（预留 AI 分析）"""
        error_lower = str(error).lower()
        if "timeout" in error_lower:
            return "timeout"
        if "quota" in error_lower or "rate limit" in error_lower:
            return "rate_limited"
        if "permission" in error_lower or "forbidden" in error_lower:
            return "permission_denied"
        if "firewall" in error_lower or "blocked" in error_lower:
            return "policy_blocked"
        return "unknown"

    def start_cleanup_thread(self, interval=300):
        """启动守护线程定期关闭超时活跃目标"""
        def _cleanup_loop():
            logger.info("[FeedbackLoop] Cleanup thread started (interval=%ds)", interval)
            while True:
                try:
                    conn = self._get_conn()
                    rows = conn.execute(
                        "SELECT DISTINCT goal_id FROM execution_tasks WHERE status='pending'"
                    ).fetchall()
                    conn.close()
                    for row in rows:
                        self.close_goal(row["goal_id"])
                except Exception as e:
                    logger.warning("[FeedbackLoop] Cleanup error: %s", e)
                time.sleep(interval)

        t = threading.Thread(target=_cleanup_loop, daemon=True, name="FeedbackCleanup")
        t.start()
        return t
