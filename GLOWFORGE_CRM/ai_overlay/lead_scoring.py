"""Lead Scoring 2.0 — 成交概率预测系统

把客户分成「能不能赚钱」，不是「有没有回复」。

评分模型:
  Score = Intent + Budget + Urgency + ProductFit + Engagement - PriceSensitivity
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ai_overlay.crm_bridge import get_customer, get_customer_messages

logger = logging.getLogger("lead_scoring")

# ── 评分权重 ────────────────────────────────────────────

WEIGHTS = {
    "intent": 0.25,           # 意图强度
    "budget": 0.15,           # 预算信号
    "urgency": 0.20,          # 紧急度
    "product_fit": 0.15,      # 产品匹配度
    "engagement": 0.15,       # 互动频率
    "price_sensitivity": -0.10,  # 价格敏感（负分）
}

# ── 评分器 ──────────────────────────────────────────────

class LeadScorer:
    """成交概率评分器"""

    @staticmethod
    def score(customer_id):
        """对客户进行成交概率评分

        返回:
            dict: {
                score: 0.0-1.0,
                tier: "HOT"/"WARM"/"COLD",
                recommended_action: str,
                conversion_probability: float,
                breakdown: dict
            }
        """
        customer = get_customer(customer_id)
        if not customer:
            return {"score": 0, "tier": "COLD", "recommended_action": "ignore"}

        messages = get_customer_messages(customer_id, limit=20)
        conv_text = " ".join(
            (m.get("content_en") or m.get("content_cn") or "") for m in messages
        ).lower()

        scores = {}

        # 1. Intent Score: 客户是否表达了明确购买意向
        intent_signals = {
            "high": ["order", "buy", "purchase", "place", "pi", "invoice",
                     "下单", "买", "订", "合同", "发票"],
            "medium": ["how much", "price", "quote", "cost", "quotation",
                       "多少钱", "报价", "价格", "怎么卖"],
            "low": ["what", "which", "tell me", "info", "information",
                    "什么", "介绍", "信息"],
        }
        high_intent = sum(1 for w in intent_signals["high"] if w in conv_text)
        medium_intent = sum(1 for w in intent_signals["medium"] if w in conv_text)
        low_intent = sum(1 for w in intent_signals["low"] if w in conv_text)
        total = high_intent + medium_intent + low_intent or 1
        scores["intent"] = min((high_intent * 1.0 + medium_intent * 0.5 + low_intent * 0.2) / total, 1.0)

        # 2. Budget Signal: 客户显示预算信号
        budget_high = ["budget", "budget is", "可以", "能做", "我的预算"]
        budget_low = ["cheap", "cheapest", "too expensive", "lower price",
                      "太贵", "便宜点", "打折", "优惠"]
        has_budget_high = any(w in conv_text for w in budget_high)
        has_budget_low = any(w in conv_text for w in budget_low)
        scores["budget"] = 0.7 if has_budget_high else (0.3 if has_budget_low else 0.5)

        # 3. Urgency Signal
        urgent_keywords = ["urgent", "asap", "need it", "rush", "today",
                           "this week", "quick", "急", "尽快", "加急", "马上"]
        has_urgent = any(w in conv_text for w in urgent_keywords)
        scores["urgency"] = 0.9 if has_urgent else 0.3

        # 4. Product Fit: 客户是否讨论了具体产品
        product_keywords = ["sign", "letter", "led", "acrylic", "stainless",
                            "metal", "neon", "发光字", "招牌", "灯箱", "亚克力"]
        product_mentions = sum(1 for w in product_keywords if w in conv_text)
        scores["product_fit"] = min(product_mentions / 3.0, 1.0)

        # 5. Engagement Frequency: 最近消息密度
        if messages:
            times = []
            for m in messages:
                ts = m.get("created_at", "")
                if ts:
                    try:
                        try:
                            times.append(datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S"))
                        except ValueError:
                            try:
                                times.append(datetime.strptime(ts[:10], "%Y-%m-%d"))
                            except ValueError:
                                continue
                    except (ValueError, TypeError):
                        continue
            if len(times) >= 2:
                span = (max(times) - min(times)).total_seconds()
                msg_count = len(messages)
                # 消息越密集分越高（每小时1条以上=高活跃）
                freq = msg_count / max(span / 3600, 1)
                scores["engagement"] = min(freq / 5.0, 1.0)
            else:
                scores["engagement"] = 0.3
        else:
            scores["engagement"] = 0.0

        # 6. Price Sensitivity（负分）
        sensitive_words = ["expensive", "too much", "discount", "cheaper",
                           "better price", "price is high", "贵", "太贵", "能便宜"]
        sensitivity = sum(1 for w in sensitive_words if w in conv_text)
        scores["price_sensitivity"] = min(sensitivity / 3.0, 1.0)

        # 汇总
        total_score = 0
        for key, weight in WEIGHTS.items():
            val = scores.get(key, 0.5)
            total_score += val * weight
        total_score = max(0.0, min(total_score, 1.0))

        # 分层 + 推荐动作
        if total_score >= 0.7:
            tier = "HOT"
            recommended = "PUSH_PI" if total_score >= 0.8 else "SEND_QUOTE"
        elif total_score >= 0.4:
            tier = "WARM"
            recommended = "NURTURE"
        else:
            tier = "COLD"
            recommended = "HOLD"

        return {
            "score": round(total_score, 3),
            "tier": tier,
            "recommended_action": recommended,
            "conversion_probability": round(total_score * 0.9, 3),
            "breakdown": {k: round(v, 3) for k, v in scores.items()},
        }

    @staticmethod
    def tier_label(tier):
        labels = {
            "HOT": "高意向 — 立即逼单",
            "WARM": "中意向 — 报价引导",
            "COLD": "低意向 — 养号培育",
        }
        return labels.get(tier, "未知")


# ── 批量评分 ────────────────────────────────────────────

def score_all_active(customer_ids):
    """批量评分，按分数排序"""
    scored = []
    for cid in customer_ids:
        r = LeadScorer.score(cid)
        scored.append({"customer_id": cid, **r})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def get_hot_leads(customer_ids, min_score=0.7):
    """获取高意向客户"""
    return [s for s in score_all_active(customer_ids) if s["score"] >= min_score]
