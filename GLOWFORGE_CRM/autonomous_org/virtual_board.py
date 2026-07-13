"""VirtualBoard — AI 管理层（CEO/COO/CFO/CMO）

4 个管理角色，每个调用对应业务引擎做决策。
board_session() 汇总 4 决策 → 写入 org_decisions。
"""
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime

logger = logging.getLogger("glowforge.virtual_board")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class CEOAgent:
    """CEO — 战略决策: 市场方向、整体策略、增长机会"""

    def __init__(self, board_ref=None):
        self._board = board_ref

    def analyze(self, context=None):
        """调用 ExecutiveDashboard + StrategyEngine + GraphEngine 做战略分析"""
        decisions = []

        # ExecutiveDashboard: 全局健康度
        try:
            from executive_dash import ExecutiveDashboard
            dash = ExecutiveDashboard()
            ceo_summary = dash.get_ceo_summary()
            financial_health = dash.get_financial_health_score()
            decisions.append({
                "agent": "CEO",
                "decision_type": "health_check",
                "summary": "全局健康度分析",
                "details": {
                    "ceo_summary": str(ceo_summary)[:200] if ceo_summary else "",
                    "financial_health": financial_health if financial_health else 0,
                },
                "impact_score": 0.5,
            })
        except Exception as e:
            logger.debug("[CEO] ExecutiveDashboard unavailable: %s", e)

        # StrategyEngine: 战略推荐
        try:
            from strategy_engine.core.strategy_engine import StrategyEngine
            se = StrategyEngine()
            recs = se.run_full_analysis(dry_run=True)
            decisions.append({
                "agent": "CEO",
                "decision_type": "strategy",
                "summary": "战略分析推荐",
                "details": {"recommendations": str(recs)[:300] if recs else ""},
                "impact_score": 0.7,
            })
        except Exception as e:
            logger.debug("[CEO] StrategyEngine unavailable: %s", e)

        # GraphEngine: 利润路径
        try:
            from business_graph.engine import GraphEngine
            ge = GraphEngine()
            paths = ge.find_profit_paths("channel", "profit", top_n=3)
            bottlenecks = ge.get_bottlenecks()
            decisions.append({
                "agent": "CEO",
                "decision_type": "profit_paths",
                "summary": "利润路径与瓶颈分析",
                "details": {
                    "top_paths": str(paths)[:200] if paths else "",
                    "bottlenecks": str(bottlenecks)[:200] if bottlenecks else "",
                },
                "impact_score": 0.6,
            })
        except Exception as e:
            logger.debug("[CEO] GraphEngine unavailable: %s", e)

        # MarketExpansionEngine: 市场扩张机会
        try:
            from strategy_engine.growth.market_expansion import MarketExpansionEngine
            mkt = MarketExpansionEngine()
            opportunities = mkt.discover_opportunities({}, {}, {})
            decisions.append({
                "agent": "CEO",
                "decision_type": "market_expansion",
                "summary": "市场扩张机会发现",
                "details": {"opportunities": str(opportunities)[:200] if opportunities else ""},
                "impact_score": 0.4,
            })
        except Exception as e:
            logger.debug("[CEO] MarketExpansionEngine unavailable: %s", e)

        if not decisions:
            decisions.append({
                "agent": "CEO",
                "decision_type": "noop",
                "summary": "所有引擎不可用，无决策",
                "details": {},
                "impact_score": 0.0,
            })

        return decisions


class CFOAgent:
    """CFO — 财务决策: 预算、利润、成本控制、资本分配"""

    def __init__(self, board_ref=None):
        self._board = board_ref

    def analyze(self, context=None):
        decisions = []

        # BudgetEngine: 预算 vs 实际
        try:
            from budget_engine import BudgetEngine
            be = BudgetEngine()
            budget_alerts = be.get_budget_alerts()
            decisions.append({
                "agent": "CFO",
                "decision_type": "budget_control",
                "summary": "预算执行监控",
                "details": {"alerts": str(budget_alerts)[:200] if budget_alerts else "无预警"},
                "impact_score": 0.6,
            })
        except Exception as e:
            logger.debug("[CFO] BudgetEngine unavailable: %s", e)

        # PLEngine: 损益趋势
        try:
            from pl_engine import PLEngine
            ple = PLEngine()
            pl_trend = ple.get_pl_trend(months=6)
            decisions.append({
                "agent": "CFO",
                "decision_type": "pl_analysis",
                "summary": "损益趋势分析",
                "details": {"trend": str(pl_trend)[:200] if pl_trend else ""},
                "impact_score": 0.7,
            })
        except Exception as e:
            logger.debug("[CFO] PLEngine unavailable: %s", e)

        # MarginEngine: 利润率
        try:
            from margin_engine import MarginEngine
            me = MarginEngine()
            margin = me.evaluate_margin("default")
            decisions.append({
                "agent": "CFO",
                "decision_type": "margin_check",
                "summary": "利润率评估",
                "details": {"margin": str(margin)[:200] if margin else ""},
                "impact_score": 0.5,
            })
        except Exception as e:
            logger.debug("[CFO] MarginEngine unavailable: %s", e)

        # ProfitGuard: 利润保护
        try:
            from profit_guard import ProfitGuardEngine
            pg = ProfitGuardEngine()
            guard = pg.evaluate(0, 0)
            decisions.append({
                "agent": "CFO",
                "decision_type": "profit_guard",
                "summary": "利润保护检查",
                "details": {"guard_result": str(guard)[:200] if guard else ""},
                "impact_score": 0.4,
            })
        except Exception as e:
            logger.debug("[CFO] ProfitGuard unavailable: %s", e)

        # CapitalAllocator: 资本分配建议
        try:
            from ai_universe.capital_allocator import CapitalAllocator
            ca = CapitalAllocator()
            allocation = ca.allocate(100000)
            decisions.append({
                "agent": "CFO",
                "decision_type": "capital_allocation",
                "summary": "资本分配建议",
                "details": {"allocation": str(allocation)[:200] if allocation else ""},
                "impact_score": 0.8,
            })
        except Exception as e:
            logger.debug("[CFO] CapitalAllocator unavailable: %s", e)

        if not decisions:
            decisions.append({
                "agent": "CFO",
                "decision_type": "noop",
                "summary": "所有引擎不可用，无决策",
                "details": {},
                "impact_score": 0.0,
            })

        return decisions


class CMOAgent:
    """CMO — 市场决策: 市场评分、活动管理、市场扩张、启动计划"""

    def __init__(self, board_ref=None):
        self._board = board_ref

    def analyze(self, context=None):
        decisions = []

        # MarketScoring: 市场评分
        try:
            from strategy_engine.market.market_scoring import MarketScoring
            ms = MarketScoring()
            top_markets = ms.get_top_markets(n=5)
            recommendations = ms.get_market_recommendation("default")
            decisions.append({
                "agent": "CMO",
                "decision_type": "market_scoring",
                "summary": "目标市场评分",
                "details": {
                    "top_markets": str(top_markets)[:200] if top_markets else "",
                    "recommendation": str(recommendations)[:200] if recommendations else "",
                },
                "impact_score": 0.6,
            })
        except Exception as e:
            logger.debug("[CMO] MarketScoring unavailable: %s", e)

        # CampaignEngine: 活动绩效
        try:
            from campaign_engine import CampaignEngine
            ce = CampaignEngine()
            campaigns = ce.get_active_campaigns() if hasattr(ce, 'get_active_campaigns') else []
            decisions.append({
                "agent": "CMO",
                "decision_type": "campaign_review",
                "summary": "营销活动回顾",
                "details": {"campaigns": str(campaigns)[:200] if campaigns else "无活跃活动"},
                "impact_score": 0.5,
            })
        except Exception as e:
            logger.debug("[CMO] CampaignEngine unavailable: %s", e)

        # MarketExpansionEngine: 扩张策略
        try:
            from strategy_engine.growth.market_expansion import MarketExpansionEngine
            mkt = MarketExpansionEngine()
            penetration = mkt.get_current_penetration("default")
            decisions.append({
                "agent": "CMO",
                "decision_type": "market_penetration",
                "summary": "市场渗透分析",
                "details": {"penetration": str(penetration)[:200] if penetration else ""},
                "impact_score": 0.4,
            })
        except Exception as e:
            logger.debug("[CMO] MarketExpansionEngine unavailable: %s", e)

        # MarketSpinup: 启动计划
        try:
            from ai_universe.market_spinup import MarketSpinup
            ms = MarketSpinup()
            spinup = ms.estimate_success_probability("default_product", "default_market")
            decisions.append({
                "agent": "CMO",
                "decision_type": "launch_readiness",
                "summary": "市场启动就绪评估",
                "details": {"success_probability": str(spinup)[:200] if spinup else ""},
                "impact_score": 0.3,
            })
        except Exception as e:
            logger.debug("[CMO] MarketSpinup unavailable: %s", e)

        if not decisions:
            decisions.append({
                "agent": "CMO",
                "decision_type": "noop",
                "summary": "所有引擎不可用，无决策",
                "details": {},
                "impact_score": 0.0,
            })

        return decisions


class COOAgent:
    """COO — 运营决策: 执行队列、资源调度、状态监管、瓶颈检测"""

    def __init__(self, board_ref=None):
        self._board = board_ref

    def analyze(self, context=None):
        decisions = []

        # ExecutionQueue: 队列状态
        try:
            from execution.execution_queue import ExecutionQueue
            eq = ExecutionQueue()
            stats = eq.get_queue_stats()
            decisions.append({
                "agent": "COO",
                "decision_type": "queue_status",
                "summary": "执行队列状态",
                "details": {"stats": stats},
                "impact_score": 0.5,
            })
        except Exception as e:
            logger.debug("[COO] ExecutionQueue unavailable: %s", e)

        # ResourceScheduler: 资源负载
        try:
            from execution.resource_scheduler import ResourceScheduler
            rs = ResourceScheduler()
            agents = rs.get_all_agents()
            overloaded = rs.redistribute_overloaded()
            decisions.append({
                "agent": "COO",
                "decision_type": "resource_load",
                "summary": "资源负载分析",
                "details": {
                    "agent_count": len(agents),
                    "overloaded_count": overloaded,
                },
                "impact_score": 0.6,
            })
        except Exception as e:
            logger.debug("[COO] ResourceScheduler unavailable: %s", e)

        # GraphEngine: 运营瓶颈
        try:
            from business_graph.engine import GraphEngine
            ge = GraphEngine()
            bottlenecks = ge.get_bottlenecks()
            leverage = ge.get_leverage_points()
            decisions.append({
                "agent": "COO",
                "decision_type": "bottleneck_analysis",
                "summary": "运营瓶颈检测",
                "details": {
                    "bottlenecks": str(bottlenecks)[:200] if bottlenecks else "无瓶颈",
                    "leverage_points": str(leverage)[:200] if leverage else "",
                },
                "impact_score": 0.7,
            })
        except Exception as e:
            logger.debug("[COO] GraphEngine unavailable: %s", e)

        # StateRegistry: 状态监管
        try:
            from safety.state_registry import StateRegistry
            sr = StateRegistry()
            divergences = sr._detect_divergences() if hasattr(sr, '_detect_divergences') else []
            decisions.append({
                "agent": "COO",
                "decision_type": "state_registry",
                "summary": "状态一致性检查",
                "details": {"divergences": str(divergences)[:200] if divergences else "无分歧"},
                "impact_score": 0.4,
            })
        except Exception as e:
            logger.debug("[COO] StateRegistry unavailable: %s", e)

        if not decisions:
            decisions.append({
                "agent": "COO",
                "decision_type": "noop",
                "summary": "所有引擎不可用，无决策",
                "details": {},
                "impact_score": 0.0,
            })

        return decisions


class VirtualBoard:
    """虚拟董事会 — 运行 4 角色分析并汇总决策到 DB"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH
        self.ceo = CEOAgent(self)
        self.cfo = CFOAgent(self)
        self.cmo = CMOAgent(self)
        self.coo = COOAgent(self)

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def board_session(self, context=None):
        """运行一次完整董事会: 4 角色分析 → 汇总 → 写入 DB"""
        session_id = uuid.uuid4().hex[:12]
        all_decisions = []

        for role_name, agent in [
            ("CEO", self.ceo),
            ("CFO", self.cfo),
            ("CMO", self.cmo),
            ("COO", self.coo),
        ]:
            try:
                decisions = agent.analyze(context)
                for d in decisions:
                    d["session_id"] = session_id
                    all_decisions.append(d)
                logger.info("[VirtualBoard] %s produced %d decisions", role_name, len(decisions))
            except Exception as e:
                logger.warning("[VirtualBoard] %s analysis failed: %s", role_name, e)

        # 写入 DB
        self._persist_decisions(session_id, all_decisions)

        return {
            "session_id": session_id,
            "board_decisions": all_decisions,
            "decision_count": len(all_decisions),
            "timestamp": datetime.now().isoformat(),
        }

    def _persist_decisions(self, session_id, decisions):
        """写入 org_decisions 表"""
        try:
            conn = self._get_conn()
            try:
                for d in decisions:
                    conn.execute(
                        """INSERT INTO org_decisions
                           (session_id, decision_type, agent, summary, details_json, impact_score, status)
                           VALUES (?, ?, ?, ?, ?, ?, 'approved')""",
                        (session_id, d.get("decision_type", ""), d.get("agent", ""),
                         d.get("summary", ""), json.dumps(d.get("details", {}), ensure_ascii=False),
                         d.get("impact_score", 0.0)),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[VirtualBoard] persisting decisions failed: %s", e)

    def get_session_decisions(self, session_id):
        """获取指定董事会会话的决策记录"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM org_decisions WHERE session_id=? ORDER BY id", (session_id,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[VirtualBoard] get_session_decisions failed: %s", e)
            return []

    def get_recent_sessions(self, limit=5):
        """获取最近 N 个董事会会话"""
        try:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT session_id, MAX(created_at) as ts FROM org_decisions "
                    "GROUP BY session_id ORDER BY ts DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("[VirtualBoard] get_recent_sessions failed: %s", e)
            return []
