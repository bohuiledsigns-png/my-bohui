"""Market Expansion Engine — 市场扩张引擎

自动发现「下一个该打的市场」。
基于 ROI 数据 + 需求趋势 + 当前渗透率 判断。

核心逻辑:
  IF ROI high AND demand rising → 扩张（增预算/扩受众）
  IF ROI low AND demand flat  → 暂缓
  IF new market found         → 尝试进入（小预算测试）
"""
import logging
from datetime import datetime

from strategy_engine.db import _read_db

logger = logging.getLogger("growth.market_expansion")

# ── 市场扩张配置 ──
MIN_ROI_FOR_EXPANSION = 2.0        # ROI 高于此值才考虑扩张
MIN_DEMAND_GROWTH = 0.05           # 最低需求增长率
NEW_MARKET_TEST_BUDGET = 0.05      # 新市场测试预算比例
EXPANSION_BUDGET_INCREASE = 0.20   # 扩张预算增幅
MAX_PENETRATION_FOR_EXPANSION = 0.6  # 渗透率低于此值才考虑扩张

# ── 预定义全局市场池 ──
GLOBAL_MARKET_POOL = [
    # 高潜力市场
    {"country": "US", "region": "NA", "tier": "core", "ad_cost_index": 1.0},
    {"country": "CA", "region": "NA", "tier": "core", "ad_cost_index": 0.9},
    {"country": "GB", "region": "EU", "tier": "core", "ad_cost_index": 0.9},
    {"country": "DE", "region": "EU", "tier": "growth", "ad_cost_index": 0.8},
    {"country": "FR", "region": "EU", "tier": "growth", "ad_cost_index": 0.8},
    {"country": "AE", "region": "MEA", "tier": "core", "ad_cost_index": 0.7},
    {"country": "SA", "region": "MEA", "tier": "growth", "ad_cost_index": 0.5},
    {"country": "QA", "region": "MEA", "tier": "growth", "ad_cost_index": 0.6},
    {"country": "KW", "region": "MEA", "tier": "growth", "ad_cost_index": 0.5},
    {"country": "JP", "region": "APAC", "tier": "core", "ad_cost_index": 1.1},
    {"country": "AU", "region": "APAC", "tier": "growth", "ad_cost_index": 0.9},
    {"country": "SG", "region": "APAC", "tier": "growth", "ad_cost_index": 0.7},
    {"country": "MY", "region": "APAC", "tier": "emerging", "ad_cost_index": 0.4},
    {"country": "TH", "region": "APAC", "tier": "emerging", "ad_cost_index": 0.3},
    {"country": "BR", "region": "LATAM", "tier": "emerging", "ad_cost_index": 0.4},
    {"country": "MX", "region": "LATAM", "tier": "emerging", "ad_cost_index": 0.4},
    # 新兴潜力市场
    {"country": "NG", "region": "MEA", "tier": "frontier", "ad_cost_index": 0.2},
    {"country": "KE", "region": "MEA", "tier": "frontier", "ad_cost_index": 0.2},
    {"country": "VN", "region": "APAC", "tier": "frontier", "ad_cost_index": 0.25},
    {"country": "ID", "region": "APAC", "tier": "frontier", "ad_cost_index": 0.3},
]


class MarketExpansionEngine:
    """市场扩张引擎 — 自动发现新市场机遇"""

    @staticmethod
    def discover_opportunities(roi_data=None, demand_data=None, market_data=None,
                                growth_state=None, dry_run=True):
        """发现市场扩张机会

        综合 ROI、需求趋势、当前市场数据，输出扩张建议。

        参数:
            roi_data: ROIEngine.calculate_roi() 输出
            demand_data: DemandAnalyzer 输出
            market_data: market_scoring.score_markets() 输出
            growth_state: growth_state.json 历史数据
            dry_run: 预览模式

        返回:
            dict: { expansion_opportunities, new_market_candidates, summary }
        """
        # ── 1. 分析现有市场扩张机会 ──
        existing_markets = MarketExpansionEngine._get_existing_market_performance(
            roi_data, market_data
        )

        expansion_ops = []
        for mkt in existing_markets:
            if MarketExpansionEngine._should_expand(mkt):
                increase_pct = (
                    EXPANSION_BUDGET_INCREASE
                    if mkt.get("roi", 0) >= MIN_ROI_FOR_EXPANSION
                    else 0.10
                )
                expansion_ops.append({
                    "market": mkt["country"],
                    "type": "expansion",
                    "current_roi": mkt.get("roi", 0),
                    "current_revenue": mkt.get("revenue", 0),
                    "current_penetration": mkt.get("penetration", 0),
                    "demand_trend": mkt.get("demand_trend", "stable"),
                    "action": "increase_budget",
                    "budget_increase_pct": increase_pct,
                    "reason": (
                        f"ROI {mkt.get('roi', 0):.1f}x + demand "
                        f"{mkt.get('demand_trend', 'stable')}"
                    ),
                    "expected_impact": MarketExpansionEngine._estimate_impact(mkt),
                })

        # ── 2. 发现新市场 ──
        active_markets = {m["country"] for m in existing_markets}
        new_candidates = MarketExpansionEngine._find_new_markets(
            active_markets, roi_data, demand_data, growth_state,
        )

        # ── 3. 排序 ──
        expansion_ops.sort(key=lambda x: x.get("current_roi", 0), reverse=True)
        new_candidates.sort(key=lambda x: x.get("potential_score", 0), reverse=True)

        return {
            "expansion_opportunities": expansion_ops,
            "new_market_candidates": new_candidates[:5],  # 最多推荐 5 个新市场
            "summary": {
                "total_expansion_ops": len(expansion_ops),
                "total_new_markets": len(new_candidates),
                "total_budget_increase": round(
                    sum(o.get("budget_increase_pct", 0) for o in expansion_ops), 2
                ),
            },
        }

    @staticmethod
    def _get_existing_market_performance(roi_data, market_data):
        """获取现有市场的表现数据"""
        markets = []

        # 从 roi_data 提取
        if roi_data:
            for src, data in roi_data.get("by_source", {}).items():
                # ad source 可能不是国家码，需要判断
                if len(src) == 2 and src.isalpha():
                    markets.append({
                        "country": src.upper(),
                        "revenue": data.get("revenue", 0),
                        "roi": data.get("roi", 0),
                        "orders": data.get("orders", 0),
                        "customers": data.get("customers", 0),
                        "demand_trend": "stable",
                        "penetration": 0.5,
                    })

        # 从 market_data 补充
        if market_data:
            for m in (market_data.get("scored_markets") or
                      market_data.get("market_strategy", {}).get("scored_markets", [])):
                country = m.get("country") or m.get("market", "")
                existing = next(
                    (x for x in markets if x["country"] == country), None
                )
                if existing:
                    existing["penetration"] = m.get("score", 50) / 100.0
                    existing["demand_trend"] = m.get("trend", "stable")
                else:
                    markets.append({
                        "country": country,
                        "revenue": 0,
                        "roi": 0,
                        "orders": 0,
                        "customers": 0,
                        "demand_trend": m.get("trend", "stable"),
                        "penetration": m.get("score", 50) / 100.0,
                    })

        return markets

    @staticmethod
    def _should_expand(market):
        """判断是否应该扩张该市场"""
        roi = market.get("roi", 0)
        penetration = market.get("penetration", 0.5)
        demand = market.get("demand_trend", "stable")

        # ROI 不够高
        if roi < MIN_ROI_FOR_EXPANSION and market.get("customers", 0) > 0:
            return False

        # 渗透率过高（已饱和）
        if penetration > MAX_PENETRATION_FOR_EXPANSION:
            return False

        # 需求下降
        if demand == "declining":
            return False

        return True

    @staticmethod
    def _estimate_impact(market):
        """预估扩张影响"""
        revenue = market.get("revenue", 0)
        roi = market.get("roi", 0)
        # 简单模型: 扩预算 20% → 收入增 15% (带衰减)
        estimated_revenue_gain = revenue * 0.15
        estimated_profit_gain = estimated_revenue_gain * (roi / (1 + roi)) if roi > 0 else 0

        return {
            "estimated_revenue_gain": round(estimated_revenue_gain, 2),
            "estimated_profit_gain": round(estimated_profit_gain, 2),
            "model_note": "conservative estimate (15% revenue lift for 20% budget increase)",
        }

    @staticmethod
    def _find_new_markets(active_markets, roi_data, demand_data, growth_state):
        """发现新市场候选"""
        candidates = []
        for pool_market in GLOBAL_MARKET_POOL:
            country = pool_market["country"]
            if country in active_markets:
                continue

            # 检查历史是否尝试过
            if growth_state:
                tried = growth_state.get("market_attempts", [])
                if country in tried:
                    continue

            # 计算潜力分
            score = MarketExpansionEngine._score_new_market(
                country, pool_market, roi_data, demand_data,
            )

            if score >= 0.3:  # 潜力分门槛
                candidates.append({
                    "market": country,
                    "region": pool_market["region"],
                    "tier": pool_market["tier"],
                    "ad_cost_index": pool_market["ad_cost_index"],
                    "potential_score": round(score, 3),
                    "suggested_budget_pct": NEW_MARKET_TEST_BUDGET,
                    "entry_strategy": (
                        "small_test"
                        if pool_market["tier"] in ("frontier", "emerging")
                        else "moderate_entry"
                    ),
                    "reason": MarketExpansionEngine._entry_reason(
                        score, pool_market,
                    ),
                })

        return candidates

    @staticmethod
    def _score_new_market(country, pool_market, roi_data, demand_data):
        """计算新市场潜力分

        维度:
          - 广告成本指数 (0.20)
          - 区域市场潜力 (0.25)
          - 相似市场 ROI (0.30)
          - 需求趋势 (0.25)
        """
        score = 0.0

        # 广告成本指数: 成本越低分越高
        cost_index = pool_market.get("ad_cost_index", 0.5)
        score += 0.20 * (1 - cost_index)  # 低成本市场加分

        # 市场层级: core=0.4, growth=0.3, emerging=0.2, frontier=0.1
        tier_scores = {"core": 0.4, "growth": 0.3, "emerging": 0.2, "frontier": 0.1}
        score += 0.25 * tier_scores.get(pool_market.get("tier", "frontier"), 0.1)

        # 相似市场 ROI: 同区域市场的平均 ROI 作为参考
        if roi_data:
            region_rois = []
            for src, data in roi_data.get("by_source", {}).items():
                if len(src) == 2 and src.isalpha():
                    region_rois.append(data.get("roi", 0))
            avg_roi = sum(region_rois) / len(region_rois) if region_rois else 0
            score += 0.30 * min(avg_roi / 5.0, 1.0)

        # 默认需求评分
        score += 0.25 * 0.5  # 中性需求

        return min(score, 1.0)

    @staticmethod
    def _entry_reason(score, pool_market):
        """生成市场推荐理由"""
        tier = pool_market["tier"]
        region = pool_market["region"]

        reasons = {
            "core": "已建立市场地位，建议加大投放",
            "growth": "高速增长市场，建议中规模进入",
            "emerging": "新兴市场，建议小规模测试",
            "frontier": "前沿市场，建议最小预算验证",
        }

        base = reasons.get(tier, "建议评估进入")
        return f"{region} {pool_market['country']} — {base} (潜力分: {score:.2f})"

    @staticmethod
    def get_current_penetration(country_code):
        """查询当前在某个国家的渗透率 (基于 DB 数据)"""
        conn = _read_db()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(DISTINCT o.id) as orders,
                    COUNT(DISTINCT c.id) as customers,
                    SUM(o.total_amount) as revenue
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.country = ?
                  AND o.status IN ('shipped', 'delivered', 'completed',
                                   'pending_approval', 'in_production')
            """, (country_code,)).fetchone()
        except Exception as e:
            logger.warning(f"Penetration query error: {e}")
            return None
        finally:
            conn.close()

        if not row or not row["customers"]:
            return {"country": country_code, "orders": 0, "customers": 0, "revenue": 0}

        return {
            "country": country_code,
            "orders": row["orders"] or 0,
            "customers": row["customers"] or 0,
            "revenue": round(row["revenue"] or 0, 2),
        }
