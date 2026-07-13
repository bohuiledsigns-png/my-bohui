"""利润保护引擎 — 防止AI在压价谈判中丢失利润"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ==================== 利润规则 ====================
# 基于现有成本+markup结构（app.py默认markup_pct=30%）
# 客户对外价 = 成本 × (1 + markup_pct)，默认1.3x
# 反向推理：cost = customer_price / 1.3

PROFIT_RULES = {
    "danger_zone": 0.30,       # 低于30% → REJECT（不能做）
    "min_margin": 0.35,        # 最低35% → ANCHOR_UPSELL（推荐升级）
    "target_margin": 0.50,     # 目标50% → ACCEPT_WITH_UPSELL（正常+推加购）
    "premium_margin": 0.65,    # 高端65% → APPROVE（直接成交）
    "default_markup": 1.3,     # 默认加价率（反向推算成本用）
}

# ==================== 利润评估器 ====================

class ProfitGuardEngine:
    """利润守卫 — 评估报价是否安全"""

    def __init__(self, rules=None):
        self.rules = rules or PROFIT_RULES

    def evaluate(self, cost, proposed_price):
        """评估报价的利润等级

        参数:
            cost: 成本价（人民币或美元均可，只要单位一致）
            proposed_price: 客户看到的价格

        返回:
            dict: {
                "decision": "REJECT" / "ANCHOR_UPSELL" /
                           "ACCEPT_WITH_UPSELL" / "APPROVE",
                "margin": float,
                "profit": float,
                "details": str
            }
        """
        if cost <= 0 or proposed_price <= 0:
            return {"decision": "REJECT", "margin": 0, "profit": 0,
                    "details": "无效成本或价格"}

        profit = proposed_price - cost
        margin = profit / cost

        if margin < self.rules["danger_zone"]:
            return {
                "decision": "REJECT",
                "margin": round(margin, 3),
                "profit": round(profit, 2),
                "details": f"Margin {margin:.1%} below danger zone {self.rules['danger_zone']:.0%}"
            }
        elif margin < self.rules["min_margin"]:
            return {
                "decision": "ANCHOR_UPSELL",
                "margin": round(margin, 3),
                "profit": round(profit, 2),
                "details": f"Margin {margin:.1%} below minimum {self.rules['min_margin']:.0%}, recommend upsell"
            }
        elif margin < self.rules["target_margin"]:
            return {
                "decision": "ACCEPT_WITH_UPSELL",
                "margin": round(margin, 3),
                "profit": round(profit, 2),
                "details": f"Margin {margin:.1%} at acceptable level, offer LED brightness/install add-on"
            }
        else:
            return {
                "decision": "APPROVE",
                "margin": round(margin, 3),
                "profit": round(profit, 2),
                "details": f"Margin {margin:.1%} above target, clean close recommended"
            }

    def evaluate_range(self, cost, price_min, price_max):
        """评估整个价格区间的利润等级（用于A/B/C tier检查）"""
        min_result = self.evaluate(cost, price_min)
        max_result = self.evaluate(cost, price_max)

        # 整体按最差情况
        worst = min(min_result["margin"], max_result["margin"])
        if worst < self.rules["danger_zone"]:
            level = "DANGER"
        elif worst < self.rules["min_margin"]:
            level = "MARGINAL"
        elif worst < self.rules["target_margin"]:
            level = "SAFE"
        else:
            level = "PREMIUM"

        return {
            "level": level,
            "min_margin": min_result["margin"],
            "max_margin": max_result["margin"],
            "min_decision": min_result["decision"],
            "max_decision": max_result["decision"],
        }


# ==================== 成本推算 ====================

def estimate_cost(assumption):
    """从假设模型估算成本价

    使用现有报价计算器的反向逻辑：
    客户价 = 成本 × markup_pct
    成本 = 客户价 / (1 + markup_pct)

    参数:
        assumption: assumption_engine.build_assumption() 输出

    返回:
        float: 估算成本（美元）
    """
    base_cost_map = {
        "backlit_led": 200,
        "neon_sign": 150,
        "channel_letters": 220,
        "acrylic_letters": 100,
        "stainless_steel": 250,
        "chromatic": 300,
    }

    sign_type = assumption.get("sign_type", "backlit_led")
    base_cost = base_cost_map.get(sign_type, 180)

    # 宽度影响
    width = assumption.get("width_m", 1.2)
    width_factor = max(0.5, width / 1.2)

    # 尝试从DB精确计算
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT price_tiers FROM products WHERE status='active' AND category IN ("
            "'3D LED发光字','不锈钢金属字','广告招牌')"
        ).fetchall()
        conn.close()
        prices = []
        for (pt,) in rows:
            try:
                tiers = json.loads(pt)
                for t in tiers if isinstance(tiers, list) else []:
                    if isinstance(t, dict) and "price" in t:
                        prices.append(float(t["price"]))
            except Exception:
                continue
        if prices:
            avg_price = sum(prices) / len(prices)
            db_cost = avg_price / PROFIT_RULES["default_markup"]
            base_cost = min(base_cost, db_cost)  # 取保守值
    except Exception:
        pass

    return base_cost * width_factor


# ==================== 响应话术 ====================

_RESPONSE_TEMPLATES = {
    "REJECT": (
        "I appreciate your budget concern. However, at this price level, "
        "we cannot guarantee the quality and durability our clients expect. "
        "We only use certified LED systems and weatherproof materials — "
        "and those have a minimum cost. "
        "The most affordable option we can offer in this category starts around "
        "USD {safe_price}. "
        "Would you like me to show you what's possible at that level?"
    ),
    "ANCHOR_UPSELL": (
        "I understand budget is important. Instead of reducing quality, "
        "let me show you an optimized configuration that fits your number "
        "while keeping durability and visibility strong. "
        "Most clients in your situation find that the slightly upgraded version "
        "performs significantly better at night. "
        "The recommended range for your setup is USD {target_range}. "
        "Want me to prepare a detailed comparison?"
    ),
    "ACCEPT_WITH_UPSELL": (
        "Good choice — this option works well for restaurants like yours. "
        "If you want, we can also upgrade the LED brightness for an additional "
        "USD 30 for better night visibility. "
        "Ready to proceed with the 30% deposit?"
    ),
    "APPROVE": (
        "Perfect — this setup is ideal for your store. "
        "I can reserve the production slot once you confirm. "
        "Shall I send the invoice for the 30% deposit?"
    ),
}


def get_response_template(decision, safe_price=None, target_range=None):
    """获取对应决策等级的话术模板"""
    template = _RESPONSE_TEMPLATES.get(decision, _RESPONSE_TEMPLATES["REJECT"])
    if safe_price:
        template = template.replace("{safe_price}", str(safe_price))
    if target_range:
        template = template.replace("{target_range}", target_range)
    return template


# ==================== 压价处理 ====================

_HANDLE_PRESSURE_TEMPLATE = (
    "I understand budget is important. "
    "Instead of reducing quality, we can adjust:\n"
    "✔ sign size slightly smaller\n"
    "✔ simpler lighting configuration\n"
    "✔ standard mounting system\n\n"
    "This keeps durability and visibility stable.\n"
    "New optimized range:\n"
    "👉 USD {new_min} – {new_max}"
)


def handle_price_pressure(cost, customer_target, assumption=None):
    """客户压价时：不降价，调配置

    返回:
        dict: {decision, response, adjusted_config, margin}
    """
    # 先评估客户目标价
    evaluation = ProfitGuardEngine().evaluate(cost, customer_target)

    if evaluation["decision"] == "REJECT":
        # 低于底线 → 给最低安全价
        safe_markup = PROFIT_RULES["min_margin"]
        safe_price = int(cost * (1 + safe_markup))
        return {
            "decision": "REJECT",
            "margin": evaluation["margin"],
            "response": get_response_template("REJECT", safe_price=safe_price),
            "adjusted_config": None,
        }

    elif evaluation["decision"] == "ANCHOR_UPSELL":
        # 利润偏薄 → 推荐升级配置
        target_price = int(cost * (1 + PROFIT_RULES["target_margin"]))
        return {
            "decision": "ANCHOR_UPSELL",
            "margin": evaluation["margin"],
            "response": get_response_template(
                "ANCHOR_UPSELL",
                target_range=f"USD {int(cost * (1 + PROFIT_RULES['min_margin']))}–{target_price}"
            ),
            "adjusted_config": None,
        }

    elif evaluation["decision"] == "ACCEPT_WITH_UPSELL":
        return {
            "decision": "ACCEPT_WITH_UPSELL",
            "margin": evaluation["margin"],
            "response": get_response_template("ACCEPT_WITH_UPSELL"),
            "adjusted_config": None,
        }

    else:
        return {
            "decision": "APPROVE",
            "margin": evaluation["margin"],
            "response": get_response_template("APPROVE"),
            "adjusted_config": None,
        }


def check_tier_prices(assumption, price_tiers):
    """批量检查A/B/C tier的价格利润安全

    参数:
        assumption: 假设模型
        price_tiers: [(label, low_price, high_price), ...]
            ex: [("Budget", 180, 240), ("Standard", 280, 350), ("Premium", 380, 450)]

    返回:
        list: [{"label": ..., "level": ..., "safe": bool}, ...]
    """
    cost = estimate_cost(assumption)
    guard = ProfitGuardEngine()
    results = []
    for label, low, high in price_tiers:
        r = guard.evaluate_range(cost, low, high)
        results.append({
            "label": label,
            "price_min": low,
            "price_max": high,
            "level": r["level"],
            "safe": r["level"] in ("SAFE", "PREMIUM"),
            "min_margin": r["min_margin"],
            "max_margin": r["max_margin"],
        })
    return results


# ==================== 快速测试 ====================
if __name__ == "__main__":
    print("=== Profit Guard Engine 测试 ===\n")

    guard = ProfitGuardEngine()

    # 测试场景
    test_cases = [
        ("高利润", 200, 400),      # margin = 100%
        ("正常利润", 200, 320),     # margin = 60%
        ("刚达标", 200, 280),       # margin = 40%
        ("偏低", 200, 250),         # margin = 25%
        ("危险区", 200, 230),       # margin = 15%
    ]

    for label, cost, price in test_cases:
        r = guard.evaluate(cost, price)
        print(f"{label}: cost={cost}, price={price} → "
              f"margin={r['margin']:.0%}, decision={r['decision']}")

    # 压价测试
    print("\n=== 压价响应测试 ===")
    r = handle_price_pressure(200, 250)  # 客户想$250，成本$200
    print(f"决策: {r['decision']}")
    print(f"话术: {r['response'][:80]}...")

    # Tier安全检查
    print("\n=== Tier安全检查 ===")
    from assumption_engine import generate_quote
    q = generate_quote({"text": "restaurant sign"})
    tiers = [
        ("Budget Acrylic", 180, 240),
        ("Standard Metal", 280, 350),
        ("Premium HD", 380, 450),
    ]
    results = check_tier_prices(q["assumption"], tiers)
    for r in results:
        icon = "✅" if r["safe"] else "⚠️"
        print(f"  {icon} {r['label']}: ${r['price_min']}-${r['price_max']} "
              f"→ margin {r['min_margin']:.0%}-{r['max_margin']:.0%} ({r['level']})")

    print("\n=== 成本估算测试 ===")
    cost = estimate_cost(q["assumption"])
    print(f"Standard restaurant sign 估算成本: USD {cost:.0f}")
    print(f"最低客户价 (35% margin): USD {cost * 1.35:.0f}")
    print(f"目标客户价 (50% margin): USD {cost * 1.5:.0f}")
