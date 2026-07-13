"""ResourceScheduler — 资源调度器

Agent 分配: 按能力/负载/客户状态匹配合适执行器。
"""
import json
import logging
import os
import sqlite3

logger = logging.getLogger("glowforge.resource_scheduler")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 默认种子 Agent 配置
DEFAULT_AGENTS = [
    {
        "agent_id": "sales_agent",
        "agent_type": "sales",
        "display_name": "销售代理",
        "capabilities": ["send_message", "send_quote", "negotiate", "followup"],
    },
    {
        "agent_id": "marketing_agent",
        "agent_type": "marketing",
        "display_name": "营销代理",
        "capabilities": ["send_catalog", "broadcast", "campaign"],
    },
    {
        "agent_id": "pricing_agent",
        "agent_type": "pricing",
        "display_name": "定价代理",
        "capabilities": ["calculate_price", "adjust_discount", "price_check"],
    },
    {
        "agent_id": "crm_agent",
        "agent_type": "crm",
        "display_name": "CRM代理",
        "capabilities": ["update_lead", "create_task", "tag_customer"],
    },
    {
        "agent_id": "content_agent",
        "agent_type": "content",
        "display_name": "内容代理",
        "capabilities": ["generate_content", "translate", "proofread"],
    },
    {
        "agent_id": "finance_agent",
        "agent_type": "finance",
        "display_name": "财务代理",
        "capabilities": ["create_invoice", "check_credit", "payment_reminder"],
    },
]


class ResourceScheduler:
    """Agent 资源调度器"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def seed_default_agents(self):
        """插入默认 Agent 配置到 execution_agents 表（如果不存在）"""
        try:
            conn = self._get_conn()
            count = 0
            for agent in DEFAULT_AGENTS:
                existing = conn.execute(
                    "SELECT COUNT(*) as c FROM execution_agents WHERE agent_id=?",
                    (agent["agent_id"],),
                ).fetchone()["c"]
                if existing == 0:
                    conn.execute(
                        """INSERT INTO execution_agents
                           (agent_id, agent_type, display_name, capabilities)
                           VALUES (?, ?, ?, ?)""",
                        (agent["agent_id"], agent["agent_type"],
                         agent["display_name"],
                         json.dumps(agent["capabilities"], ensure_ascii=False)),
                    )
                    count += 1
            conn.commit()
            conn.close()
            logger.info("[ResourceScheduler] Seeded %d default agents", count)
            return count
        except Exception as e:
            logger.warning("[ResourceScheduler] seed failed: %s", e)
            return 0

    def schedule_task(self, task, agents):
        """按 capability 匹配 + 负载均衡选择 Agent.

        Args:
            task: dict with 'task_type' key
            agents: list of BaseAgent instances

        Returns:
            agent_id (str) or None
        """
        task_type = task.get("task_type", "")
        suitable = [a for a in agents if a.can_handle(task_type)]
        if not suitable:
            return None
        # 负载均衡: 选 active_tasks 最少的
        return min(suitable, key=lambda a: a.active_tasks).agent_id

    def assign_task(self, task_id, agent_id):
        """记录 Agent 分配到 execution_tasks 表"""
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE execution_tasks SET assigned_agent=? WHERE id=?",
                (agent_id, task_id),
            )
            conn.execute(
                "UPDATE execution_agents SET current_load=current_load+1 WHERE agent_id=?",
                (agent_id,),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning("[ResourceScheduler] assign_task failed: %s", e)
            return False

    def get_agent_load(self, agent_id):
        """获取当前 Agent 处理中任务数"""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT current_load FROM execution_agents WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
            conn.close()
            return row["current_load"] if row else 0
        except Exception:
            return 0

    def get_all_agents(self):
        """获取所有注册 Agent"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM execution_agents WHERE is_active=1"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[ResourceScheduler] get_all_agents failed: %s", e)
            return []

    def redistribute_overloaded(self, threshold=2.0):
        """负载 > 2x 均值时重新分配（预留）"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT agent_id, current_load FROM execution_agents WHERE is_active=1"
            ).fetchall()
            conn.close()
            loads = [r["current_load"] for r in rows]
            if not loads:
                return 0
            avg = sum(loads) / len(loads)
            overloaded = [r for r in rows if r["current_load"] > avg * threshold]
            return len(overloaded)
        except Exception:
            return 0
