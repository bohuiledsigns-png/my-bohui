"""V2.0 Revenue Orchestrator Core — 收入操作系统总中枢

职责:
  1. composite_decision() — 并行运行 V1 decide() + V2 ProfitScore，合并输出
  2. start_services() — 启动策略循环 + 原有跟进引擎
  3. get_dashboard() — 聚合所有子系统核心指标

组合所有 V2 子系统 + 对接 V1.3:
  - v2_profit_engine      — 6维利润评分
  - v2_dynamic_pricing    — 4因子动态定价
  - v2_campaign_intel     — 智能营销
  - v2_market_expansion   — 市场拓展
  - v2_strategy_loop      — 策略闭环
  - V1.3 orchestrator     — 现有销售推进引擎

约束:
  - 不改任何已有文件（仅 __init__.py 加一行 import）
  - 默认 dry_run=True
"""
import os
import sys
import json
import logging
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("v2_core")


# ── 子系统引用（延迟加载） ──────────────────────────────

class V2Subsystems:
    """V2 子系统容器（延迟加载，避免循环依赖）"""

    _profit = None
    _pricing = None
    _campaign = None
    _market = None
    _strategy = None

    @classmethod
    def profit(cls):
        if cls._profit is None:
            from ai_overlay.v2_profit_engine import ProfitEngine
            cls._profit = ProfitEngine
        return cls._profit

    @classmethod
    def pricing(cls):
        if cls._pricing is None:
            from ai_overlay.v2_dynamic_pricing import DynamicPricingEngine
            cls._pricing = DynamicPricingEngine
        return cls._pricing

    @classmethod
    def campaign(cls):
        if cls._campaign is None:
            from ai_overlay.v2_campaign_intel import CampaignIntelEngine
            cls._campaign = CampaignIntelEngine
        return cls._campaign

    @classmethod
    def market(cls):
        if cls._market is None:
            from ai_overlay.v2_market_expansion import MarketExpansionEngine
            cls._market = MarketExpansionEngine
        return cls._market

    @classmethod
    def strategy(cls):
        if cls._strategy is None:
            from ai_overlay.v2_strategy_loop import StrategyLoop
            cls._strategy = StrategyLoop
        return cls._strategy


# ── V1.3 引用 ─────────────────────────────────────────────

_V1_ORCHESTRATOR = None


def _get_v1_orchestrator():
    global _V1_ORCHESTRATOR
    if _V1_ORCHESTRATOR is None:
        from ai_overlay.orchestrator import decide as v1_decide
        _V1_ORCHESTRATOR = v1_decide
    return _V1_ORCHESTRATOR


# =============================================================
#  Revenue Orchestrator Core
# =============================================================

class RevenueOrchestrator:
    """Revenue OS 总中枢"""

    # ── 复合决策 ──────────────────────────────────────────

    @staticmethod
    def composite_decision(customer_id, message_text, extra_context=None, dry_run=True):
        """并行运行 V1 decide() + V2 ProfitScore，合并输出

        参数:
            customer_id: CRM 客户 ID
            message_text: 客户最新消息
            extra_context: 可选上下文
            dry_run: V2 部分不写入数据库

        返回:
            dict: {
                v1: { ... V1 decide 结果 ... },
                v2: {
                    profit: { profit_score, tier, dimensions },
                    pricing: { final_price, margin, discount_allowed },
                },
                composite: {
                    tier_override: str or None,
                    suggested_action: str,
                    profit_signal: str,
                }
            }
        """
        start = time.time()

        # 1. V1 决策（销售推进）
        try:
            v1 = _get_v1_orchestrator()(customer_id, message_text, extra_context)
        except Exception as e:
            logger.error(f"V1 decide failed: {e}")
            v1 = {"error": str(e), "action": "error"}

        # 2. V2 利润评分
        try:
            profit_result = V2Subsystems.profit().score(customer_id, dry_run=dry_run)
        except Exception as e:
            logger.error(f"V2 profit score failed: {e}")
            profit_result = {"error": str(e), "tier": "LOW", "profit_score": 0}

        # 3. V2 动态定价
        try:
            pricing_result = V2Subsystems.pricing().calculate(
                customer_id, dry_run=dry_run
            )
        except Exception as e:
            logger.error(f"V2 pricing failed: {e}")
            pricing_result = {"error": str(e)}

        # 4. 合成决策
        profit_tier = profit_result.get("tier", "LOW")
        v1_action = v1.get("action", "reply")
        v1_state = v1.get("state", "NEW")

        # Profit Tier 覆盖建议
        tier_override = None
        suggested_action = v1_action
        profit_signal = "neutral"

        if profit_tier == "HIGH_VALUE":
            tier_override = "FAST_CLOSE"
            profit_signal = "positive"
            # 高利润客户：提升动作
            if v1_action in ("reply",):
                suggested_action = "prioritize"
        elif profit_tier == "LOW":
            tier_override = "DEFER"
            profit_signal = "negative"
            # 低利润客户：保守
            if v1_action in ("escalate",):
                suggested_action = "reply"

        elapsed = round((time.time() - start) * 1000, 1)

        result = {
            "v1": {
                "state": v1.get("state"),
                "action": v1.get("action"),
                "intent": v1.get("intent"),
                "confidence": v1.get("confidence"),
                "reply": v1.get("reply", ""),
                "safe_to_execute": v1.get("safe_to_execute", True),
            },
            "v2": {
                "profit": {
                    "profit_score": profit_result.get("profit_score"),
                    "tier": profit_tier,
                    "dimensions": profit_result.get("dimensions"),
                    "orders_count": profit_result.get("orders_count"),
                },
                "pricing": {
                    "final_price": pricing_result.get("final_price"),
                    "margin": pricing_result.get("margin"),
                    "discount_allowed": pricing_result.get("discount_allowed"),
                    "price_range": pricing_result.get("price_range"),
                },
            },
            "composite": {
                "tier_override": tier_override,
                "suggested_action": suggested_action,
                "profit_signal": profit_signal,
                "elapsed_ms": elapsed,
            },
        }

        # V2 建议不影响 V1 原始决策（只作为旁路信息）
        logger.info(
            f"[Composite] cid={customer_id} "
            f"v1_action={v1_action} v2_tier={profit_tier} "
            f"signal={profit_signal} elapsed={elapsed}ms"
        )

        return result

    # ── 仪表盘 ────────────────────────────────────────────

    @staticmethod
    def get_dashboard(dry_run=True):
        """聚合所有子系统的核心指标

        返回:
            dict: {
                profit_engine: { top_tiers, ... },
                market_expansion: { top_markets, ... },
                strategy: { focus_product, ... },
                campaign: { segment_counts, ... },
                timestamp: str,
            }
        """
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run,
        }

        # 1. Strategy Loop 分析
        try:
            strategy = V2Subsystems.strategy().run_daily_analysis(dry_run=True)
            dashboard["strategy"] = {
                "focus_product": strategy.get("focus_product"),
                "focus_region": strategy.get("focus_region"),
                "followup_speed": strategy.get("followup_speed"),
                "discount_policy": strategy.get("discount_policy"),
            }
            dashboard["details"] = strategy.get("details", {})
        except Exception as e:
            logger.warning(f"Strategy analysis failed: {e}")
            dashboard["strategy"] = {"error": str(e)}

        # 2. Market Expansion
        try:
            markets = V2Subsystems.market().score_all_markets()
            dashboard["market_expansion"] = {
                "top_markets": markets[:5] if markets else [],
                "regions": V2Subsystems.market().get_region_summary(),
                "budget_allocation": V2Subsystems.market().recommend_budget_allocation(),
            }
        except Exception as e:
            logger.warning(f"Market expansion failed: {e}")
            dashboard["market_expansion"] = {"error": str(e)}

        # 3. Campaign
        try:
            segments = V2Subsystems.campaign().list_segments()
            dashboard["campaign"] = {
                "segment_counts": {
                    k: {"name": v["name"], "count": v["count"]}
                    for k, v in segments.items()
                },
                "total_prospects": sum(
                    v["count"] for v in segments.values()
                ),
            }
        except Exception as e:
            logger.warning(f"Campaign analysis failed: {e}")
            dashboard["campaign"] = {"error": str(e)}

        return dashboard

    # ── 服务启动 ──────────────────────────────────────────

    @staticmethod
    def start_services():
        """启动 V2 后台服务

        包括:
          1. 策略循环定时器（每24小时）
          2. 原有跟进引擎（来自 V1.3）
        """
        logger.info("V2.0 Revenue OS 服务启动中...")
        logger.info("  子系统就绪: Profit / Pricing / Campaign / Market / Strategy")

        # 启动策略循环（单次立即执行）
        try:
            strategy_result = V2Subsystems.strategy().run_daily_analysis(dry_run=True)
            logger.info(f"  初始策略分析完成: focus={strategy_result.get('focus_product')}")
        except Exception as e:
            logger.warning(f"  初始策略分析失败: {e}")

        # 启动 V1 跟进引擎
        try:
            from ai_overlay.followup_engine import start_followup_engine
            eng = start_followup_engine(check_interval=300)
            logger.info("  跟进引擎: 运行中 (每5分钟检查)")
        except Exception as e:
            logger.warning(f"  跟进引擎启动失败: {e}")
            eng = None

        logger.info("V2.0 Revenue OS 服务已就绪")
        return eng

    @staticmethod
    def stop_services(engine=None):
        """停止 V2 后台服务"""
        if engine:
            try:
                engine.stop()
            except Exception:
                pass
        logger.info("V2.0 Revenue OS 服务已停止")


# =============================================================
#  快捷入口
# =============================================================

def composite_decision(customer_id, message_text, extra_context=None, dry_run=True):
    """一站式复合决策"""
    return RevenueOrchestrator.composite_decision(
        customer_id, message_text, extra_context, dry_run
    )


def get_dashboard(dry_run=True):
    """获取仪表盘"""
    return RevenueOrchestrator.get_dashboard(dry_run)


def start_services():
    """启动服务"""
    return RevenueOrchestrator.start_services()
