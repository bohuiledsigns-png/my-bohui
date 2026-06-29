"""V2.0 Market Expansion — 市场拓展引擎

Geo Score 模型:
  Geo Score = ShippingCost(-0.15) + AvgOrderValue(0.30)
              + ConversionRate(0.25) + MarginPotential(0.20) + MarketSize(0.10)

复用:
  - ai_engine/market_explorer.py 的 MARKET_SCORES + 评分逻辑
  - region_engine.py             的区域数据 + 汇率
  - profit_engine.py             的国家利润参数

约束:
  - 纯数学计算，不调 AI API
  - 默认 dry_run=True
"""
import os
import sys
import json
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger("v2_market_expansion")

# ── 评分权重 ──────────────────────────────────────────────

GEO_WEIGHTS = {
    "shipping_cost": -0.15,
    "avg_order_value": 0.30,
    "conversion_rate": 0.25,
    "margin_potential": 0.20,
    "market_size": 0.10,
}

# ── 市场数据结构 ──────────────────────────────────────────

MARKET_DATA = {
    "US": {"name": "美国", "region": "NA", "shipping_cost": 0.7,
           "avg_order_value": 0.9, "conversion_rate": 0.6,
           "margin_potential": 0.7, "market_size": 0.95,
           "currency": "USD", "profit_profile": "high"},
    "CA": {"name": "加拿大", "region": "NA", "shipping_cost": 0.65,
           "avg_order_value": 0.8, "conversion_rate": 0.55,
           "margin_potential": 0.65, "market_size": 0.3,
           "currency": "USD", "profit_profile": "medium_high"},
    "GB": {"name": "英国", "region": "EU", "shipping_cost": 0.55,
           "avg_order_value": 0.8, "conversion_rate": 0.55,
           "margin_potential": 0.6, "market_size": 0.4,
           "currency": "GBP", "profit_profile": "medium_high"},
    "DE": {"name": "德国", "region": "EU", "shipping_cost": 0.55,
           "avg_order_value": 0.85, "conversion_rate": 0.5,
           "margin_potential": 0.6, "market_size": 0.5,
           "currency": "EUR", "profit_profile": "medium"},
    "FR": {"name": "法国", "region": "EU", "shipping_cost": 0.55,
           "avg_order_value": 0.75, "conversion_rate": 0.45,
           "margin_potential": 0.55, "market_size": 0.4,
           "currency": "EUR", "profit_profile": "medium"},
    "AE": {"name": "阿联酋", "region": "MEA", "shipping_cost": 0.5,
           "avg_order_value": 0.95, "conversion_rate": 0.8,
           "margin_potential": 0.9, "market_size": 0.25,
           "currency": "AED", "profit_profile": "very_high"},
    "SA": {"name": "沙特", "region": "MEA", "shipping_cost": 0.45,
           "avg_order_value": 0.9, "conversion_rate": 0.75,
           "margin_potential": 0.85, "market_size": 0.3,
           "currency": "SAR", "profit_profile": "very_high"},
    "QA": {"name": "卡塔尔", "region": "MEA", "shipping_cost": 0.45,
           "avg_order_value": 0.85, "conversion_rate": 0.7,
           "margin_potential": 0.85, "market_size": 0.1,
           "currency": "QAR", "profit_profile": "very_high"},
    "AU": {"name": "澳大利亚", "region": "APAC", "shipping_cost": 0.5,
           "avg_order_value": 0.85, "conversion_rate": 0.55,
           "margin_potential": 0.65, "market_size": 0.25,
           "currency": "AUD", "profit_profile": "medium_high"},
    "SG": {"name": "新加坡", "region": "APAC", "shipping_cost": 0.5,
           "avg_order_value": 0.8, "conversion_rate": 0.6,
           "margin_potential": 0.7, "market_size": 0.1,
           "currency": "SGD", "profit_profile": "high"},
    "JP": {"name": "日本", "region": "APAC", "shipping_cost": 0.5,
           "avg_order_value": 0.75, "conversion_rate": 0.45,
           "margin_potential": 0.6, "market_size": 0.5,
           "currency": "JPY", "profit_profile": "medium"},
    "MY": {"name": "马来西亚", "region": "APAC", "shipping_cost": 0.6,
           "avg_order_value": 0.5, "conversion_rate": 0.5,
           "margin_potential": 0.45, "market_size": 0.2,
           "currency": "MYR", "profit_profile": "medium"},
    "SG": {"name": "新加坡", "region": "APAC", "shipping_cost": 0.5,
           "avg_order_value": 0.8, "conversion_rate": 0.6,
           "margin_potential": 0.7, "market_size": 0.1,
           "currency": "SGD", "profit_profile": "high"},
}


class MarketExpansionEngine:
    """市场拓展引擎 — Geo Score 国家评分与预算分配"""

    @staticmethod
    def _try_load_from_db():
        """尝试从 DB 获取实际市场数据（降级到静态数据）"""
        try:
            from ai_engine.market_explorer import MarketExplorer
            explorer = MarketExplorer()
            analysis = explorer.analyze_markets()
            if analysis and len(analysis) > 0:
                return analysis
        except Exception:
            pass
        return None

    @staticmethod
    def _try_load_market_pricing(country):
        """尝试从 market_pricing 表获取实际利润数据"""
        try:
            import sqlite3
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "crm_data.db"
            )
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT mp.target_margin, mp.min_margin "
                "FROM market_pricing mp "
                "JOIN regions r ON mp.region_id = r.id "
                "JOIN region_countries rc ON rc.region_id = r.id "
                "WHERE rc.country_code=? LIMIT 1",
                (country,)
            ).fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception:
            pass
        return None

    @staticmethod
    def score_all_markets(use_db=False):
        """对所有已知市场进行 Geo Score 评分

        参数:
            use_db: 尝试加载 DB 实际数据

        返回:
            list: 按 Geo Score 降序排列，每项含所有评分维度 + 总分
        """
        results = []

        for code, data in MARKET_DATA.items():
            # 尝试 DB 数据修正
            margin_extra = 0
            if use_db:
                mp = MarketExpansionEngine._try_load_market_pricing(code)
                if mp:
                    margin_extra = mp.get("target_margin", 0.5) - 0.5

            score = (
                GEO_WEIGHTS["shipping_cost"] * data["shipping_cost"]
                + GEO_WEIGHTS["avg_order_value"] * data["avg_order_value"]
                + GEO_WEIGHTS["conversion_rate"] * data["conversion_rate"]
                + GEO_WEIGHTS["margin_potential"] * (data["margin_potential"] + margin_extra)
                + GEO_WEIGHTS["market_size"] * data["market_size"]
            )

            # 归一化到 0-100: 理论范围 [-0.15, 0.75] → [0, 100]
            normalized = max(0, min(100, (score + 0.15) / 0.90 * 100))

            results.append({
                "country_code": code,
                "country_name": data["name"],
                "region": data["region"],
                "geo_score": round(normalized, 2),
                "dimensions": {
                    "shipping_cost": data["shipping_cost"],
                    "avg_order_value": data["avg_order_value"],
                    "conversion_rate": data["conversion_rate"],
                    "margin_potential": data["margin_potential"],
                    "market_size": data["market_size"],
                },
                "profit_profile": data["profit_profile"],
                "recommendation": (
                    "strong_buy" if normalized >= 70 else
                    "buy" if normalized >= 50 else
                    "hold" if normalized >= 30 else
                    "weak"
                ),
            })

        results.sort(key=lambda x: x["geo_score"], reverse=True)
        return results

    @staticmethod
    def recommend_budget_allocation():
        """根据 Geo Score 推荐预算分配

        返回:
            dict: { country_code: allocation_pct, ... }
        """
        markets = MarketExpansionEngine.score_all_markets()
        if not markets:
            return {}

        # 取前5名并归一化分配
        top5 = markets[:5]
        total_score = sum(m["geo_score"] for m in top5)
        if total_score <= 0:
            return {}

        allocation = {}
        for m in top5:
            pct = round(m["geo_score"] / total_score * 100, 1)
            allocation[m["country_code"]] = {
                "pct": pct,
                "name": m["country_name"],
                "score": m["geo_score"],
                "recommendation": m["recommendation"],
            }
        return allocation

    @staticmethod
    def get_market_insights(country_code):
        """获取单个市场分析

        返回:
            dict: { country, geo_score, dimensions, competitors, strategy, entry_cost }
        """
        markets = MarketExpansionEngine.score_all_markets()
        target = None
        for m in markets:
            if m["country_code"] == country_code.upper():
                target = m
                break

        if not target:
            return {"error": f"Unknown country: {country_code}"}

        # 竞争分析
        competition_map = {
            "NA": "high", "EU": "high",
            "MEA": "low", "APAC": "medium",
            "LATAM": "medium",
        }

        # 进入成本估算
        entry_cost_map = {
            "NA": "high", "EU": "high",
            "MEA": "medium", "APAC": "medium",
            "LATAM": "low",
        }

        # 推荐策略
        score = target["geo_score"]
        if score >= 70:
            strategy = "积极进入，优先分配销售资源"
        elif score >= 50:
            strategy = "测试市场，控制预算逐步扩展"
        elif score >= 30:
            strategy = "观察等待，仅处理 inbound 询盘"
        else:
            strategy = "暂不进入"

        return {
            "country_code": target["country_code"],
            "country_name": target["country_name"],
            "region": target["region"],
            "geo_score": target["geo_score"],
            "dimensions": target["dimensions"],
            "competition_level": competition_map.get(target["region"], "medium"),
            "entry_cost": entry_cost_map.get(target["region"], "medium"),
            "profit_profile": target["profit_profile"],
            "strategy": strategy,
        }

    @staticmethod
    def get_region_summary():
        """获取区域汇总统计"""
        markets = MarketExpansionEngine.score_all_markets()
        regions = {}
        for m in markets:
            r = m["region"]
            if r not in regions:
                regions[r] = {
                    "countries": [],
                    "total_score": 0,
                    "count": 0,
                }
            regions[r]["countries"].append(m["country_code"])
            regions[r]["total_score"] += m["geo_score"]
            regions[r]["count"] += 1

        for r in regions:
            regions[r]["avg_score"] = round(
                regions[r]["total_score"] / regions[r]["count"], 2
            ) if regions[r]["count"] > 0 else 0
            regions[r]["best_country"] = max(
                regions[r]["countries"],
                key=lambda c: next(
                    (m["geo_score"] for m in markets if m["country_code"] == c), 0
                )
            )

        return regions
