"""V9: Autonomous Business Organization — 配置常量"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 部门默认预算百分比
DEFAULT_BUDGET_PCT = {
    "sales": 0.35,        # 销售部 35%
    "marketing": 0.20,    # 市场部 20%
    "finance": 0.10,      # 财务部 10%
    "operations": 0.15,   # 运营部 15%
    "production": 0.10,   # 生产部 10%
    "customer_success": 0.10,  # 客户成功 10%
}

# 部门 KPI 定义
DEPARTMENT_KPIS = {
    "sales": ["revenue", "conversion_rate", "avg_order_value", "win_rate"],
    "marketing": ["leads_generated", "campaign_roi", "channel_coverage"],
    "finance": ["margin", "cost_control", "cash_flow"],
    "operations": ["task_completion", "response_time", "queue_depth"],
    "production": ["output_volume", "quality_score", "on_time_rate"],
    "customer_success": ["satisfaction", "retention_rate", "repeat_orders"],
}

# 董事会循环间隔（秒）
BOARD_INTERVAL = 3600  # 1小时

# 决策循环间隔（秒）
DECISION_LOOP_INTERVAL = 600  # 10分钟

# 预算再平衡间隔（秒）
REBALANCE_INTERVAL = 86400  # 每天

# 预算调整最大幅度（单次）
MAX_BUDGET_ADJUSTMENT = 0.10  # 10%

# 风险阈值
RISK_THRESHOLDS = {
    "revenue_drop": 0.15,      # 收入下降 >15% 触发预警
    "margin_floor": 0.20,      # 利润率低于 20% 预警
    "cost_overrun": 0.10,      # 成本超支 >10% 预警
    "conversion_drop": 0.10,   # 转化率下降 >10% 预警
}

# 部门协作路由表
COLLABORATION_ROUTES = {
    ("sales", "marketing"): ["request_leads", "share_campaign_feedback"],
    ("marketing", "sales"): ["send_leads", "campaign_results"],
    ("marketing", "finance"): ["request_budget", "report_roi"],
    ("finance", "operations"): ["approve_budget", "report_spend"],
    ("operations", "production"): ["dispatch_tasks", "capacity_check"],
    ("production", "customer_success"): ["quality_alert", "delivery_update"],
    ("customer_success", "sales"): ["upsell_opportunity", "churn_warning"],
}

# 启动默认部门（含 budget_pct，供 DepartmentSystem 使用）
DEFAULT_DEPARTMENTS = [
    {"dept_id": "sales", "name": "销售部", "head_agent": "sales_agent", "budget_pct": 0.35},
    {"dept_id": "marketing", "name": "市场部", "head_agent": "marketing_agent", "budget_pct": 0.20},
    {"dept_id": "finance", "name": "财务部", "head_agent": "finance_agent", "budget_pct": 0.10},
    {"dept_id": "operations", "name": "运营部", "head_agent": "crm_agent", "budget_pct": 0.15},
    {"dept_id": "production", "name": "生产部", "head_agent": "pricing_agent", "budget_pct": 0.10},
    {"dept_id": "customer_success", "name": "客户成功部", "head_agent": "content_agent", "budget_pct": 0.10},
]
