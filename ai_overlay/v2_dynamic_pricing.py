"""V2.0 Dynamic Pricing — 4因子动态定价引擎

核心公式:
  final_price = base_price × region_factor × urgency_factor × competition_factor × profit_modifier

复用:
  - price_optimizer.py 的价格锚点
  - region_engine.py   的区域系数/汇率
  - dynamic_pricing.py  的国家弹性
  - profit_guard.py     的利润阈值
  - market_pricing 表的定价系数

约束:
  - 纯数学计算，不调 AI API
  - 默认 dry_run=True
"""
import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
logger = logging.getLogger("v2_dynamic_pricing")

# ── 默认定价系数 ──────────────────────────────────────────

REGION_FACTORS = {
    "NA": 1.40, "EU": 1.35, "MEA": 1.35,
    "APAC": 1.25, "LATAM": 1.30,
}

URGENCY_FACTORS = {"high": 1.10, "medium": 1.00, "low": 0.95}

COMPETITION_FACTORS = {"low": 1.15, "medium": 1.00, "high": 0.90}

PROFIT_MODIFIER_DEFAULT = 1.0

# ── 默认价格锚点（降级方案） ──────────────────────────────

DEFAULT_ANCHORS = {
    "LOW": {"label": "经济款", "price_range": "$150-250", "anchor": "$200"},
    "MID": {"label": "热销款", "price_range": "$250-400", "anchor": "$320"},
    "HIGH": {"label": "旗舰款", "price_range": "$400-600", "anchor": "$500"},
}


def _read_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


class DynamicPricingEngine:
    """动态定价引擎 — base_price × 4因子"""

    @staticmethod
    def _get_region_factor(country):
        """获取区域定价系数"""
        try:
            from region_engine import RegionEngine
            re = RegionEngine()
            region = re.get_region_for_country(country)
            code = region.get("code", "APAC")
            return REGION_FACTORS.get(code, 1.30)
        except Exception:
            # 基于国家代码的快速匹配
            c = (country or "").upper()
            if c in ("US", "CA"):
                return 1.40
            if c in ("GB", "DE", "FR", "ES", "IT", "NL"):
                return 1.35
            if c in ("AE", "SA", "QA", "KW", "OM", "BH"):
                return 1.35
            return 1.30

    @staticmethod
    def _get_urgency_factor(urgency):
        """获取紧迫度系数"""
        return URGENCY_FACTORS.get(urgency, 1.00)

    @staticmethod
    def _get_competition_factor(country):
        """获取竞争系数（基于国家市场）"""
        # 高竞争市场: US, GB, DE
        high_comp = ("US", "GB", "DE", "CA", "AU")
        # 低竞争市场: MEA 大部分
        low_comp = ("AE", "SA", "QA", "KW", "OM", "IQ")
        c = (country or "").upper()
        if c in high_comp:
            return 0.90
        if c in low_comp:
            return 1.15
        return 1.00

    @staticmethod
    def _get_profit_modifier(customer_id):
        """获取利润修正系数（基于 Profit Engine 评分）"""
        conn = _read_db()
        try:
            row = conn.execute(
                "SELECT price_tier_override FROM v4_customer_state WHERE customer_id=?",
                (customer_id,)
            ).fetchone()
        except Exception:
            row = None
        finally:
            conn.close()

        if row and row["price_tier_override"]:
            tier = row["price_tier_override"]
            if tier == "HIGH_VALUE":
                return 1.15  # 高利润客户可加价
            if tier == "LOW":
                return 0.92  # 低利润客户降价促单
        return 1.0

    @staticmethod
    def _get_base_cost(product_category, default_cost=200):
        """从 production_costs 表获取基准成本"""
        conn = _read_db()
        try:
            row = conn.execute(
                "SELECT base_cost FROM production_costs "
                "WHERE product_category=? AND effective_to IS NULL "
                "ORDER BY effective_from DESC LIMIT 1",
                (product_category,)
            ).fetchone()
            if row and row["base_cost"]:
                return float(row["base_cost"])
        except Exception:
            pass
        finally:
            conn.close()
        return default_cost

    @staticmethod
    def _get_market_pricing(country, product_category):
        """从 market_pricing 获取定价系数"""
        conn = _read_db()
        try:
            row = conn.execute(
                "SELECT mp.target_margin, mp.min_margin, mp.competitor_factor "
                "FROM market_pricing mp "
                "JOIN regions r ON mp.region_id = r.id "
                "JOIN region_countries rc ON rc.region_id = r.id "
                "WHERE rc.country_code=? AND mp.product_category=? "
                "LIMIT 1",
                ((country or "").upper(), product_category)
            ).fetchone()
            if row:
                return dict(row)
        except Exception:
            pass
        finally:
            conn.close()
        return None

    @staticmethod
    def calculate(customer_id, product_category="general", base_cost=None,
                  urgency="medium", country=None, dry_run=True):
        """计算动态定价

        参数:
            customer_id: 客户 ID
            product_category: 产品分类
            base_cost: 基准成本（None 则自动查询）
            urgency: 紧迫度 (high/medium/low)
            country: 国家代码（None 则从客户信息获取）
            dry_run: 仅计算不存储

        返回:
            dict: {
                final_price: float,
                price_range: (min, max),
                discount_allowed: float,
                margin: float,
                factors: { region, urgency, competition, profit_modifier },
                base_cost: float,
                country: str,
                tier: str,
            }
        """
        # 1. 获取客户国家
        if not country:
            conn = _read_db()
            try:
                row = conn.execute(
                    "SELECT country FROM customers WHERE id=?", (customer_id,)
                ).fetchone()
                country = row["country"] if row else "UNKNOWN"
            finally:
                conn.close()

        # 2. 获取基准成本
        if base_cost is None:
            base_cost = DynamicPricingEngine._get_base_cost(product_category)

        # 3. 获取市场定价系数
        market = DynamicPricingEngine._get_market_pricing(country, product_category)

        # 4. 计算各因子
        region_factor = DynamicPricingEngine._get_region_factor(country)
        urgency_factor = DynamicPricingEngine._get_urgency_factor(urgency)
        competition_factor = DynamicPricingEngine._get_competition_factor(country)
        profit_modifier = DynamicPricingEngine._get_profit_modifier(customer_id)

        # 5. 计算最终价格
        final_price = base_cost * region_factor * urgency_factor * competition_factor * profit_modifier

        # 6. 利润计算
        margin = (final_price - base_cost) / final_price if final_price > 0 else 0

        # 7. 允许折扣
        target_margin = (market or {}).get("target_margin", 0.50)
        min_margin = (market or {}).get("min_margin", 0.35)
        discount_allowed = max(0, min(
            (final_price - base_cost * (1 + min_margin)) / final_price,
            0.25
        ))

        # 8. 价格区间
        price_min = base_cost * (1 + min_margin)
        price_max = final_price

        # 9. Tier 判断
        if margin >= 0.65:
            tier = "PREMIUM"
        elif margin >= 0.50:
            tier = "HIGH"
        elif margin >= 0.35:
            tier = "STANDARD"
        else:
            tier = "LOW_MARGIN"

        result = {
            "final_price": round(final_price, 2),
            "price_range": (round(price_min, 2), round(price_max, 2)),
            "discount_allowed": round(discount_allowed, 4),
            "margin": round(margin, 4),
            "factors": {
                "region": round(region_factor, 2),
                "urgency": round(urgency_factor, 2),
                "competition": round(competition_factor, 2),
                "profit_modifier": round(profit_modifier, 2),
            },
            "base_cost": round(base_cost, 2),
            "country": country,
            "tier": tier,
            "product_category": product_category,
        }

        if not dry_run:
            logger.info(
                f"[Pricing] cid={customer_id} cost={base_cost} "
                f"final={final_price:.2f} tier={tier} margin={margin:.1%}"
            )

        return result

    @staticmethod
    def get_quote_price(customer_id, product_category="general", quantity=1,
                         urgency="medium", country=None, dry_run=True):
        """易用封装：获取报价价格

        返回:
            dict: {
                unit_price: float,
                total_price: float,
                discount_allowed: float,
                margin: float,
                price_tier: str,
                anchors: { LOW, MID, HIGH },
                recommended_tier: str,
            }
        """
        calc = DynamicPricingEngine.calculate(
            customer_id, product_category, urgency=urgency,
            country=country, dry_run=dry_run
        )

        unit_price = calc["final_price"]
        total_price = unit_price * quantity

        # 选择推荐价格档位
        anchors = DEFAULT_ANCHORS.copy()

        # 尝试从 price_optimizer 加载真实锚点
        try:
            from price_optimizer import PriceOptimizer
            po = PriceOptimizer()
            current = po.get_current_anchors()
            if current:
                anchors = current
        except Exception:
            pass

        # 根据利润 tier 推荐价格档位
        if calc["tier"] in ("PREMIUM", "HIGH"):
            recommended = "HIGH"
        elif calc["tier"] == "STANDARD":
            recommended = "MID"
        else:
            recommended = "LOW"

        result = {
            "unit_price": round(unit_price, 2),
            "total_price": round(total_price, 2),
            "quantity": quantity,
            "discount_allowed": calc["discount_allowed"],
            "margin": calc["margin"],
            "price_tier": calc["tier"],
            "recommended_tier": recommended,
            "anchors": anchors,
        }

        return result
