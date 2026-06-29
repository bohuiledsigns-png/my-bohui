"""V2.0 Profit Engine — 6维利润评分模型

核心公式:
  Profit Score = Revenue(0.25) + Margin(0.20) + PaymentReliability(0.15)
                 + ShippingEfficiency(0.10) + RepeatProbability(0.20) - CommCost(0.10)

Tier:
  HIGH_VALUE (>=0.7) → 优先推进、快速成交
  MEDIUM     (>=0.4) → 标准处理
  LOW        (<0.4)  → 延后/低优先级

复用:
  - profit_engine.py 的国家利润参数
  - profit_guard.py  的利润阈值
  - v4_customer_state.price_tier_override 存储

约束:
  - 纯数学+SQL计算，不调 AI API
  - 全部默认 dry_run=True
"""
import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
logger = logging.getLogger("v2_profit_engine")

# ── 评分权重 ──────────────────────────────────────────────

WEIGHTS = {
    "revenue": 0.25,
    "margin": 0.20,
    "payment_reliability": 0.15,
    "shipping_efficiency": 0.10,
    "repeat_probability": 0.20,
    "comm_cost": -0.10,
}

# ── Tier 阈值 ────────────────────────────────────────────

TIER_THRESHOLDS = {
    "HIGH_VALUE": 0.70,
    "MEDIUM": 0.40,
    "LOW": 0.00,
}

# ── 利润系数（从 profit_engine 同步） ─────────────────────

COUNTRY_MARGIN_FACTORS = {
    "US": 0.65, "CA": 0.60,
    "GB": 0.58, "DE": 0.55, "FR": 0.52,
    "AE": 0.70, "SA": 0.72, "QA": 0.75,
    "AU": 0.60, "SG": 0.62, "JP": 0.55,
}

# ── 只读 DB 辅助 ─────────────────────────────────────────

def _read_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


class ProfitEngine:
    """6维利润评分引擎"""

    # ── 维度评分 ──────────────────────────────────────────

    @staticmethod
    def _score_revenue(customer_id, orders):
        """收入维度: 总金额归一化到 [0,1]"""
        if not orders:
            return 0.0
        total = sum(o.get("total_amount", 0) or 0 for o in orders)
        # 阶梯映射: $0→0, $500→0.3, $2000→0.6, $5000+→1.0
        if total <= 0:
            return 0.0
        if total >= 5000:
            return 1.0
        return total / 5000.0

    @staticmethod
    def _score_margin(customer_id, orders):
        """利润维度: 平均利润率归一化到 [0,1]"""
        if not orders:
            return 0.0
        margins = []
        for o in orders:
            total = o.get("total_amount", 0) or 0
            # 从订单计算利润率（使用各字段）
            profit = o.get("profit", 0) or 0
            if total > 0 and profit > 0:
                margins.append(profit / total)
        if not margins:
            return 0.0
        avg_margin = sum(margins) / len(margins)
        # 映射: 0%→0, 35%→0.5, 50%→0.8, 65%+→1.0
        if avg_margin <= 0:
            return 0.0
        if avg_margin >= 0.65:
            return 1.0
        return avg_margin / 0.65

    @staticmethod
    def _score_payment_reliability(customer_id, orders):
        """付款可靠性: 定金+尾款按时支付"""
        if not orders:
            return 0.0
        reliable = 0
        for o in orders:
            deposit = o.get("deposit_received", 0) or 0
            balance = o.get("balance_received", 0) or 0
            if deposit and balance:
                reliable += 1
            elif deposit:
                reliable += 0.5
        return reliable / len(orders) if orders else 0.0

    @staticmethod
    def _score_shipping_efficiency(customer_id, orders):
        """物流效率: 有无 shipping_info, 订单状态"""
        if not orders:
            return 0.0
        shipped = sum(1 for o in orders
                      if (o.get("shipping_info") or "").strip()
                      or o.get("status") in ("shipped", "delivered", "completed"))
        return shipped / len(orders) if orders else 0.0

    @staticmethod
    def _score_repeat_probability(customer_id, orders, days_since_first=365):
        """复购概率: 订单数×频率"""
        if not orders:
            return 0.0
        count = len(orders)
        if count >= 5:
            return 1.0
        if count >= 3:
            return 0.8
        if count >= 2:
            return 0.5
        return 0.2  # 只有1单

    @staticmethod
    def _score_comm_cost(customer_id, orders):
        """沟通成本: 消息总量负向"""
        conn = _read_db()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE customer_id=?",
                (customer_id,)
            ).fetchone()
            msg_count = row["cnt"] if row else 0
        finally:
            conn.close()
        # 大量消息 = 高沟通成本
        if msg_count <= 10:
            return 0.0  # 无惩罚
        if msg_count <= 30:
            return 0.2
        if msg_count <= 60:
            return 0.5
        return 0.8  # 60+消息，高成本

    # ── 国家利润修正 ──────────────────────────────────────

    @staticmethod
    def _country_profit_bonus(country):
        """国家利润修正系数 [0.8, 1.2]"""
        factor = COUNTRY_MARGIN_FACTORS.get((country or "").upper(), 0.50)
        return 0.8 + factor * 0.4  # 映射到 [0.8, 1.2]

    # ── 主评分 ────────────────────────────────────────────

    @staticmethod
    def score(customer_id, dry_run=True):
        """计算客户的 6 维利润评分

        参数:
            customer_id: CRM 客户 ID
            dry_run: 仅计算不存储

        返回:
            dict: {
                profit_score: float [0,1],
                tier: str,
                dimensions: { revenue, margin, payment_reliability,
                              shipping_efficiency, repeat_probability, comm_cost },
                orders_count: int,
                country_bonus: float,
                country: str,
                details: str
            }
        """
        # 1. 获取客户信息
        conn = _read_db()
        try:
            cust = conn.execute(
                "SELECT id, country FROM customers WHERE id=?", (customer_id,)
            ).fetchone()
            if not cust:
                return {"error": "customer_not_found", "profit_score": 0, "tier": "LOW"}
            country = cust["country"] or ""

            # 2. 获取订单历史
            order_rows = conn.execute(
                "SELECT * FROM orders WHERE customer_id=? ORDER BY created_at DESC",
                (customer_id,)
            ).fetchall()
        finally:
            conn.close()

        orders = [dict(r) for r in order_rows]

        # 3. 计算各维度
        dims = {
            "revenue": ProfitEngine._score_revenue(customer_id, orders),
            "margin": ProfitEngine._score_margin(customer_id, orders),
            "payment_reliability": ProfitEngine._score_payment_reliability(customer_id, orders),
            "shipping_efficiency": ProfitEngine._score_shipping_efficiency(customer_id, orders),
            "repeat_probability": ProfitEngine._score_repeat_probability(customer_id, orders),
            "comm_cost": ProfitEngine._score_comm_cost(customer_id, orders),
        }

        # 4. 加权总分
        raw_score = sum(
            WEIGHTS[k] * v for k, v in dims.items()
        )
        # 国家修正
        country_bonus = ProfitEngine._country_profit_bonus(country)
        profit_score = min(raw_score * country_bonus, 1.0)

        # 5. 定级
        if profit_score >= TIER_THRESHOLDS["HIGH_VALUE"]:
            tier = "HIGH_VALUE"
        elif profit_score >= TIER_THRESHOLDS["MEDIUM"]:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        # 6. 存储到 v4_customer_state（非 dry_run）
        if not dry_run:
            conn2 = _read_db()
            try:
                conn2.execute(
                    "UPDATE v4_customer_state SET price_tier_override=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE customer_id=?",
                    (tier, customer_id)
                )
                conn2.commit()
            except Exception:
                pass
            finally:
                conn2.close()

        return {
            "profit_score": round(profit_score, 4),
            "tier": tier,
            "dimensions": {k: round(v, 4) for k, v in dims.items()},
            "orders_count": len(orders),
            "country_bonus": round(country_bonus, 4),
            "country": country,
            "details": (
                f"ProfitScore={profit_score:.2f} → {tier} "
                f"({len(orders)} orders, country={country}, bonus={country_bonus:.2f})"
            ),
        }

    @staticmethod
    def score_many(customer_ids, dry_run=True):
        """批量评分多个客户"""
        results = {}
        for cid in customer_ids:
            results[cid] = ProfitEngine.score(cid, dry_run=dry_run)
        return results

    @staticmethod
    def get_tier_strategy(tier):
        """获取 Tier 对应的处理策略"""
        strategies = {
            "HIGH_VALUE": {
                "label": "高利润客户 — 优先推进快速成交",
                "action": "FAST_CLOSE",
                "discount_limit": 0.15,
                "priority": "high",
                "suggested_followup": "1天跟进",
                "auto_escalate": True,
            },
            "MEDIUM": {
                "label": "中等利润客户 — 标准处理",
                "action": "STANDARD",
                "discount_limit": 0.10,
                "priority": "normal",
                "suggested_followup": "3天跟进",
                "auto_escalate": False,
            },
            "LOW": {
                "label": "低利润客户 — 延后/批量处理",
                "action": "DEFER",
                "discount_limit": 0.05,
                "priority": "low",
                "suggested_followup": "7天跟进",
                "auto_escalate": False,
            },
        }
        return strategies.get(tier, strategies["LOW"])
