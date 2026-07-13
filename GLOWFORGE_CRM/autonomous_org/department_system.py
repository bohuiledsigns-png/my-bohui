"""DepartmentSystem — 6 部门系统

部门管理：初始化、KPI 更新、绩效评估、预算百分比。
每个部门有状态（active/frozen/closed）和绩效评分。
"""
import json
import logging
import os
import sqlite3

logger = logging.getLogger("glowforge.department_system")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 从 config.py 读取默认部门定义（单数据源）
try:
    from autonomous_org.config import DEFAULT_DEPARTMENTS
except ImportError:
    DEFAULT_DEPARTMENTS = []

DEFAULT_KPIS = {
    "sales": {"revenue": 0, "conversion_rate": 0, "avg_order_value": 0, "win_rate": 0},
    "marketing": {"leads_generated": 0, "campaign_roi": 0, "channel_coverage": 0},
    "finance": {"margin": 0, "cost_control": 0, "cash_flow": 0},
    "operations": {"task_completion": 0, "response_time": 0, "queue_depth": 0},
    "production": {"output_volume": 0, "quality_score": 0, "on_time_rate": 0},
    "customer_success": {"satisfaction": 0, "retention_rate": 0, "repeat_orders": 0},
}


class Department:
    """部门实体"""

    def __init__(self, dept_id=None, name=None, head_agent="", budget_pct=0.0,
                 performance=0.0, status="active", kpis=None, row=None):
        if row:
            self.dept_id = row["dept_id"]
            self.name = row["name"]
            self.head_agent = row["head_agent"]
            self.budget_pct = row["budget_pct"]
            self.performance = row["performance"]
            self.status = row["status"]
            raw_kpi = row["kpi_json"] if "kpi_json" in row.keys() else "{}"
            self.kpis = self._parse_kpis(raw_kpi)
        else:
            self.dept_id = dept_id
            self.name = name
            self.head_agent = head_agent
            self.budget_pct = budget_pct
            self.performance = performance
            self.status = status
            self.kpis = kpis or {}

    def _parse_kpis(self, raw):
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            "dept_id": self.dept_id,
            "name": self.name,
            "head_agent": self.head_agent,
            "budget_pct": self.budget_pct,
            "performance": self.performance,
            "status": self.status,
            "kpis": self.kpis,
        }


class DepartmentSystem:
    """部门管理系统"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        """初始化默认部门（如不存在）"""
        count = 0
        try:
            conn = self._get_conn()
            try:
                for dept in DEFAULT_DEPARTMENTS:
                    existing = conn.execute(
                        "SELECT COUNT(*) as c FROM org_departments WHERE dept_id=?",
                        (dept["dept_id"],),
                    ).fetchone()["c"]
                    if existing == 0:
                        kpis = json.dumps(DEFAULT_KPIS.get(dept["dept_id"], {}), ensure_ascii=False)
                        conn.execute(
                            """INSERT INTO org_departments
                               (dept_id, name, head_agent, budget_pct, kpi_json)
                               VALUES (?, ?, ?, ?, ?)""",
                            (dept["dept_id"], dept["name"], dept["head_agent"],
                             dept["budget_pct"], kpis),
                        )
                        count += 1
                conn.commit()
            finally:
                conn.close()
            logger.info("[DeptSystem] Initialized %d departments", count)
        except Exception as e:
            logger.warning("[DeptSystem] initialize failed: %s", e)
        return count

    def get_department(self, dept_id):
        """获取单个部门"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM org_departments WHERE dept_id=?", (dept_id,)
                ).fetchone()
                return Department(row=row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[DeptSystem] get_department failed: %s", e)
            return None

    def list_departments(self, status=None):
        """列出部门"""
        try:
            conn = self._get_conn()
            try:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM org_departments WHERE status=? ORDER BY dept_id",
                        (status,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM org_departments ORDER BY dept_id"
                    ).fetchall()
                return [Department(row=r).to_dict() for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[DeptSystem] list_departments failed: %s", e)
            return []

    def update_kpi(self, dept_id, kpi_name, value):
        """更新部门 KPI"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT kpi_json FROM org_departments WHERE dept_id=?",
                    (dept_id,),
                ).fetchone()
                if not row:
                    return False
                kpis = json.loads(row["kpi_json"]) if row["kpi_json"] else {}
                kpis[kpi_name] = value
                conn.execute(
                    "UPDATE org_departments SET kpi_json=?, updated_at=CURRENT_TIMESTAMP WHERE dept_id=?",
                    (json.dumps(kpis, ensure_ascii=False), dept_id),
                )
                conn.commit()
            finally:
                conn.close()
            # 触发绩效重算（独立连接）
            self.calculate_performance(dept_id)
            return True
        except Exception as e:
            logger.warning("[DeptSystem] update_kpi failed: %s", e)
            return False

    def calculate_performance(self, dept_id):
        """根据 KPI 计算部门绩效评分 0.0–1.0"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT kpi_json FROM org_departments WHERE dept_id=?",
                    (dept_id,),
                ).fetchone()
                if not row:
                    return 0.0
                kpis = json.loads(row["kpi_json"]) if row["kpi_json"] else {}
                if not kpis:
                    return 0.0

                # 归一化每个 KPI 到 [0, 1] 区间（假设 Max 值为 1000）
                scores = []
                for v in kpis.values():
                    if isinstance(v, (int, float)):
                        normalized = min(max(v / 1000.0, 0.0), 1.0)
                        scores.append(normalized)
                performance = sum(scores) / len(scores) if scores else 0.0

                conn.execute(
                    "UPDATE org_departments SET performance=?, updated_at=CURRENT_TIMESTAMP WHERE dept_id=?",
                    (round(performance, 4), dept_id),
                )
                conn.commit()
                return performance
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[DeptSystem] calculate_performance failed: %s", e)
            return 0.0

    def set_status(self, dept_id, status):
        """设置部门状态"""
        if status not in ("active", "frozen", "closed"):
            return False
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE org_departments SET status=?, updated_at=CURRENT_TIMESTAMP WHERE dept_id=?",
                    (status, dept_id),
                )
                conn.commit()
            finally:
                conn.close()
            return True
        except Exception as e:
            logger.warning("[DeptSystem] set_status failed: %s", e)
            return False

    def set_budget_pct(self, dept_id, pct):
        """调整部门预算百分比"""
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE org_departments SET budget_pct=?, updated_at=CURRENT_TIMESTAMP WHERE dept_id=?",
                    (pct, dept_id),
                )
                conn.commit()
            finally:
                conn.close()
            return True
        except Exception as e:
            logger.warning("[DeptSystem] set_budget_pct failed: %s", e)
            return False
