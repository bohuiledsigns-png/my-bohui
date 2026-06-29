"""V4 Dynamic Pricing — 实时动态定价系统

根据客户状态、活跃度、国家自动调整报价档位。
不是固定报价，而是"实时利润优化"。

调价逻辑:
  - FINAL + 高活跃 → 切 HIGH 档（涨价）
  - BUDGET → 保持 MID 档
  - OBJECTION → 切 LOW 档（稳定报价，不降但换方案）
  - price_sensitive_countries → LOW 档锚点
"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db


# ==================== 价格敏感国家配置 ====================

_PRICE_SENSITIVE_COUNTRIES = {
    "LOW": ["India", "IND", "Pakistan", "PAK", "Bangladesh", "BGD",
            "Nigeria", "NGA", "Kenya", "KEN", "Vietnam", "VNM",
            "Philippines", "PHL", "Indonesia", "IDN", "Egypt", "EGY"],
    "HIGH": ["USA", "US", "UK", "GBR", "Germany", "DEU", "Australia", "AUS",
             "Canada", "CAN", "Switzerland", "CHE", "Singapore", "SGP",
             "United Arab Emirates", "UAE", "ARE", "Saudi Arabia", "SAU"],
}

_STATE_TO_TIER = {
    "FINAL": "HIGH",
    "BUDGET": "MID",
    "NEW": "MID",
    "NEEDS_ANALYSIS": "MID",
    "OBJECTION": "LOW",
}

# 高活跃阈值：平均回复时间 < 2小时
_HIGH_ENGAGEMENT_HOURS = 2


class DynamicPricing:
    """动态定价系统"""

    def get_pricing_for_customer(self, customer_id):
        """获取客户当前定价

        Args:
            customer_id: 客户 ID

        Returns:
            dict: {price_tier, reason, anchors}
        """
        conn = get_db()

        # 1. 获取客户国家和状态
        cust = conn.execute(
            "SELECT country, status FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()
        if not cust:
            conn.close()
            return {"error": "customer not found"}

        country = (cust["country"] or "").upper()

        # 2. 获取 v3 最新状态
        conv = conn.execute(
            """SELECT final_state, conversion_score
               FROM v3_conversions
               WHERE customer_id=? AND final_result != 'open'
               ORDER BY id DESC LIMIT 1""",
            (customer_id,)
        ).fetchone()

        # 3. 获取 v4 状态
        v4 = conn.execute(
            """SELECT price_tier_override, price_anchors_json,
                      avg_reply_speed_hours, last_activity_at
               FROM v4_customer_state WHERE customer_id=?""",
            (customer_id,)
        ).fetchone()

        conn.close()

        # 如果有手动覆盖，直接返回
        if v4 and v4["price_tier_override"]:
            tier = v4["price_tier_override"]
            anchors = self._load_anchors_for_tier(tier)
            return {
                "customer_id": customer_id,
                "price_tier": tier,
                "reason": "manual_override",
                "anchors": anchors,
                "overridden": True,
            }

        # 动态计算
        state = conv["final_state"] if conv else "NEW"
        tier = _STATE_TO_TIER.get(state, "MID")

        # 国家修正
        if country in [c.upper() for c in _PRICE_SENSITIVE_COUNTRIES["LOW"]]:
            # 价格敏感国家 -> 最多 MID
            if tier == "HIGH":
                tier = "MID"
        elif country in [c.upper() for c in _PRICE_SENSITIVE_COUNTRIES["HIGH"]]:
            # 高利润国家，如果 final 状态则提档
            if state == "FINAL":
                tier = "HIGH"

        # 高活跃修正
        if v4 and v4["avg_reply_speed_hours"] is not None:
            if v4["avg_reply_speed_hours"] < _HIGH_ENGAGEMENT_HOURS and state == "FINAL":
                tier = "HIGH"

        reason = f"state:{state}→tier:{tier}"
        anchors = self._load_anchors_for_tier(tier)

        return {
            "customer_id": customer_id,
            "price_tier": tier,
            "reason": reason,
            "anchors": anchors,
            "overridden": False,
        }

    def apply_override(self, customer_id, price_tier, reason="manual"):
        """手动覆盖客户价格档位

        Args:
            customer_id: 客户 ID
            price_tier: 目标档位 (LOW/MID/HIGH)
            reason: 覆盖原因

        Returns:
            dict: 操作结果
        """
        if price_tier not in ("LOW", "MID", "HIGH"):
            return {"error": "invalid tier, must be LOW/MID/HIGH"}

        old_tier = self._get_current_tier(customer_id)
        anchors = self._load_anchors_for_tier(price_tier)

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM v4_customer_state WHERE customer_id=?",
            (customer_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE v4_customer_state SET
                   price_tier_override=?, price_anchors_json=?,
                   discount_reason=?, pricing_updated_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE customer_id=?""",
                (price_tier, json.dumps(anchors, ensure_ascii=False),
                 reason, customer_id)
            )
        else:
            conn.execute(
                """INSERT INTO v4_customer_state
                   (customer_id, price_tier_override, price_anchors_json,
                    discount_reason, pricing_updated_at)
                   VALUES (?,?,?,?, CURRENT_TIMESTAMP)""",
                (customer_id, price_tier,
                 json.dumps(anchors, ensure_ascii=False), reason)
            )

        # 审计日志
        conn.execute(
            """INSERT INTO v4_pricing_history
               (customer_id, old_tier, new_tier, reason, triggered_by)
               VALUES (?,?,?,?,?)""",
            (customer_id, old_tier, price_tier, reason, "manual")
        )
        conn.commit()
        conn.close()

        # 动态更新全局 price anchors
        self._apply_to_sales_executor(price_tier, anchors)

        return {
            "ok": True,
            "customer_id": customer_id,
            "old_tier": old_tier,
            "new_tier": price_tier,
            "reason": reason,
        }

    def clear_override(self, customer_id):
        """清除客户价格覆盖"""
        conn = get_db()
        conn.execute(
            "UPDATE v4_customer_state SET price_tier_override=NULL, price_anchors_json=NULL, updated_at=CURRENT_TIMESTAMP WHERE customer_id=?",
            (customer_id,)
        )
        conn.commit()
        conn.close()
        return {"ok": True, "customer_id": customer_id}

    def load_dynamic_anchors(self):
        """加载所有客户定价覆盖到 sales_executor._PRICE_ANCHORS

        在调度器启动时调用，或在 app.py 启动时调用。
        覆盖写入销售执行器的全局价格配置，影响所有消息的报价生成。
        """
        conn = get_db()
        rows = conn.execute(
            """SELECT customer_id, price_tier_override, price_anchors_json
               FROM v4_customer_state
               WHERE price_tier_override IS NOT NULL AND price_anchors_json IS NOT NULL"""
        ).fetchall()
        conn.close()

        merged = {}
        for r in rows:
            merged[r["price_tier_override"]] = json.loads(r["price_anchors_json"])

        if merged:
            try:
                import sales_executor
                sales_executor._PRICE_ANCHORS.update(merged)
            except Exception:
                pass

        return {"loaded": len(rows), "tiers": list(merged.keys())}

    def adjust_for_state(self, customer_id, state, engagement_hours=0):
        """根据状态和活跃度调整定价（供 RevenueEngine 调用）

        Args:
            customer_id: 客户 ID
            state: 当前销售状态
            engagement_hours: 平均回复间隔（小时）

        Returns:
            dict: 定价信息
        """
        # 检查是否有手动覆盖
        conn = get_db()
        override = conn.execute(
            "SELECT price_tier_override FROM v4_customer_state WHERE customer_id=? AND price_tier_override IS NOT NULL",
            (customer_id,)
        ).fetchone()
        conn.close()

        if override:
            return self.get_pricing_for_customer(customer_id)

        tier = _STATE_TO_TIER.get(state, "MID")

        if state == "FINAL" and engagement_hours < _HIGH_ENGAGEMENT_HOURS:
            tier = "HIGH"

        anchors = self._load_anchors_for_tier(tier)
        return {
            "price_tier": tier,
            "reason": f"state:{state} eng:{engagement_hours}h",
            "anchors": anchors,
        }

    # ==================== 内部方法 ====================

    def _get_current_tier(self, customer_id):
        """获取客户当前档位"""
        conn = get_db()
        row = conn.execute(
            "SELECT price_tier_override FROM v4_customer_state WHERE customer_id=?",
            (customer_id,)
        ).fetchone()
        conn.close()
        return row["price_tier_override"] if row and row["price_tier_override"] else "GLOBAL"

    def _load_anchors_for_tier(self, tier):
        """从 sales_executor._PRICE_ANCHORS 加载指定档位的配置"""
        try:
            import sales_executor
            return sales_executor._PRICE_ANCHORS.get(tier, {})
        except Exception:
            return {
                "range": "$200-350",
                "anchor": "$280",
                "abc": [
                    {"label": "A — 实用款", "price": "$200-250", "desc": "可靠耐用"},
                    {"label": "B — 热销款", "price": "$250-300", "desc": "最受客户欢迎"},
                    {"label": "C — 旗舰款", "price": "$300-350", "desc": "高端质感"},
                ],
                "risk_framing": "",
            }

    def _apply_to_sales_executor(self, tier, anchors):
        """将定价覆盖应用到 sales_executor 全局"""
        try:
            import sales_executor
            sales_executor._PRICE_ANCHORS[tier] = anchors
        except Exception:
            pass


# ==================== 快捷入口 ====================

pricing = DynamicPricing()


def load_v4_dynamic_anchors():
    """启动时调用，加载 v4 定价覆盖"""
    return pricing.load_dynamic_anchors()
