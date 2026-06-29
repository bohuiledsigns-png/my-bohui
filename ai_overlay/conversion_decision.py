"""Conversion Decision Engine — 成交决策引擎

核心问题: 「什么时候推成交？」

不是简单地看分数，而是综合分析:
  1. LeadScorer 分数阈值（>=0.65 可推）
  2. 客户语言信号（OK/yes/let's do it）
  3. 对话轮次和深度（至少3轮以上才推）
  4. 客户是否已得到所有答案
  5. 客户在比价还是真要买

输出:
  - should_close: bool — 是否应该推成交
  - method: str — 推荐成交方式 (direct_pi / send_pi / propose_payment)
  - close_score: float — 成交信心分
  - signals: [str] — 检测到的成交信号
  - reason: str — 判断理由
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("conversion_decision")

# ── 成交信号定义 ──────────────────────────────────────────

CLOSE_SIGNALS = {
    # 直接成交信号（高置信度）
    "direct_yes": {
        "keywords": [
            "yes", "ok", "deal", "agree", "let's do it", "proceed",
            "i want", "send me", "i'll take", "order", "下单", "可以做",
            "确认", "好的", "来",
        ],
        "weight": 0.90,
    },
    "asks_pi": {
        "keywords": [
            "pi", "invoice", "proforma", "proforma invoice",
            "形式发票", "合同", "发票",
        ],
        "weight": 0.95,
    },
    "asks_payment": {
        "keywords": [
            "how to pay", "payment", "deposit", "tt", "paypal",
            "western union", "怎么付", "付款", "定金", "首付",
        ],
        "weight": 0.85,
    },
    "asks_delivery": {
        "keywords": [
            "delivery time", "lead time", "how long", "when ready",
            "shipping time", "how soon", "交期", "多久", "什么时候能",
        ],
        "weight": 0.70,
    },
    "asks_logistics": {
        "keywords": [
            "shipping", "freight", "ship to", "海运", "空运", "运费",
            "cif", "fob", "delivery address",
        ],
        "weight": 0.65,
    },
    "confirms_specs": {
        "keywords": [
            "confirm", "confirmed", "sure", "that's right", "correct",
            "确认规格", "没错", "是的", "对的",
        ],
        "weight": 0.60,
    },
    "asks_quality": {
        "keywords": [
            "quality", "warranty", "certification", "guarantee",
            "质量", "质保", "保修", "认证",
        ],
        "weight": 0.50,
    },
}

# 成交方法映射
CLOSE_METHODS = {
    "direct_pi": {
        "label": "直接发PI",
        "description": "客户意向明确，直接发送形式发票推进成交",
        "min_score": 0.80,
    },
    "send_pi": {
        "label": "应要求发PI",
        "description": "客户明确索要PI/发票，立即发送",
        "min_score": 0.70,
    },
    "propose_payment": {
        "label": "提议付款",
        "description": "引导客户确认付款方式和细节",
        "min_score": 0.65,
    },
    "nurture": {
        "label": "继续培育",
        "description": "成交信号不足，继续对话培育",
        "min_score": 0.0,
    },
}


class ConversionDecisionEngine:
    """成交决策引擎 — 判断何时推进成交"""

    # 最低对话轮次要求（至少3轮才考虑推成交）
    MIN_CONVERSATION_ROUNDS = 3
    # 最低成交分数
    MIN_CLOSE_SCORE = 0.60

    @staticmethod
    def evaluate(customer_id, lead_score, state, message_text, history):
        """评估是否需要推进成交

        参数:
            customer_id: 客户ID
            lead_score: LeadScorer 评分 (0-1)
            state: 当前销售状态
            message_text: 客户最新消息
            history: 消息历史 (list of dict)

        返回:
            dict: {
                should_close: bool,
                close_score: float,
                method: str,
                signals: [str],
                conversation_rounds: int,
                reason: str
            }
        """
        t = (message_text or "").lower()
        signals_found = []
        total_signal_weight = 0.0

        # 1. 检测当前消息中的成交信号
        for key, config in CLOSE_SIGNALS.items():
            if any(kw in t for kw in config["keywords"]):
                signals_found.append(config)
                total_signal_weight = max(total_signal_weight, config["weight"])

        # 2. 回溯最近3条历史消息，检测历史信号
        recent = (history or [])[:3]
        for m in recent:
            content = (m.get("content_en") or m.get("content_cn") or "").lower()
            for key, config in CLOSE_SIGNALS.items():
                if any(kw in content for kw in config["keywords"]):
                    # 历史信号权重打8折
                    adjusted = config["weight"] * 0.8
                    if adjusted > total_signal_weight:
                        total_signal_weight = adjusted

        # 3. 计算对话轮次
        conversation_rounds = len(history or []) // 2  # 一来一回算一轮

        # 4. 综合计算成交分数
        close_score = 0.0

        # 信号权重 (50%)
        close_score += total_signal_weight * 0.5

        # LeadScorer 贡献 (30%)
        close_score += (lead_score or 0) * 0.3

        # 状态贡献 (20%)
        state_bonus = {
            "CLOSING": 0.20,
            "HOT": 0.15,
            "NEGOTIATING": 0.10,
            "PRICING": 0.05,
        }
        close_score += state_bonus.get(state, 0) * 0.2

        close_score = min(close_score, 1.0)

        # 5. 对话轮次过滤（至少N轮才考虑成交）
        if conversation_rounds < ConversionDecisionEngine.MIN_CONVERSATION_ROUNDS:
            return {
                "should_close": False,
                "close_score": round(close_score, 2),
                "method": "nurture",
                "signals": [c.get("label", k) for k, c in CLOSE_SIGNALS.items()
                           if any(kw in t for kw in c["keywords"])],
                "conversation_rounds": conversation_rounds,
                "reason": f"对话仅{conversation_rounds}轮 < 最低{ConversionDecisionEngine.MIN_CONVERSATION_ROUNDS}轮，继续培育",
            }

        # 6. 成交决策
        should_close = close_score >= ConversionDecisionEngine.MIN_CLOSE_SCORE

        if not should_close:
            return {
                "should_close": False,
                "close_score": round(close_score, 2),
                "method": "nurture",
                "signals": [c.get("label", k) for k, c in CLOSE_SIGNALS.items()
                           if any(kw in t for kw in c["keywords"])],
                "conversation_rounds": conversation_rounds,
                "reason": f"成交分={close_score:.2f} < 阈值={ConversionDecisionEngine.MIN_CLOSE_SCORE}，暂不推成交",
            }

        # 7. 选择成交方法
        method = "nurture"
        if close_score >= CLOSE_METHODS["direct_pi"]["min_score"]:
            method = "direct_pi"
        elif close_score >= CLOSE_METHODS["send_pi"]["min_score"]:
            method = "send_pi"
        elif close_score >= CLOSE_METHODS["propose_payment"]["min_score"]:
            method = "propose_payment"

        # 如果有特定信号，覆盖方法选择
        if any(kw in t for kw in CLOSE_SIGNALS["asks_pi"]["keywords"]):
            method = "send_pi"

        return {
            "should_close": True,
            "close_score": round(close_score, 2),
            "method": method,
            "signals": [c.get("label", k) for k, c in CLOSE_SIGNALS.items()
                       if any(kw in t for kw in c["keywords"])],
            "conversation_rounds": conversation_rounds,
            "reason": (
                f"成交分={close_score:.2f} >= 阈值={ConversionDecisionEngine.MIN_CLOSE_SCORE}, "
                f"方法={CLOSE_METHODS.get(method, {}).get('label', method)}, "
                f"信号={[s for s in signals_found]}"
            ),
        }

    @staticmethod
    def get_close_suggestions(method):
        """获取成交方法的建议执行动作"""
        suggestions = {
            "direct_pi": {
                "action": "quote",
                "priority": "high",
                "message": "客户成交信号强，直接生成PI推进",
            },
            "send_pi": {
                "action": "quote",
                "priority": "high",
                "message": "客户索要PI，立即生成发送",
            },
            "propose_payment": {
                "action": "reply",
                "priority": "normal",
                "message": "引导客户确认付款方式",
            },
        }
        return suggestions.get(method, {"action": "reply", "priority": "normal"})
