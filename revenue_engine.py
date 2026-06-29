"""Revenue Engine — WhatsApp 自动收单引擎

将 WhatsApp 消息转化为可执行的成交动作。
是整个 CRM 的"大脑"：判断状态 → 决定动作 → 生成回复 → 触发报价。

管道:
  message
    → state (sales_state)
    → behavior (sales_executor)
    → reply (AI生成)
    → action (quote / close / ask)
    → conversion_score
    → WhatsApp output

设计原则:
  - 每条消息都推进成交概率
  - 不解释技术，只推进成交
  - 永远带价格锚 + A/B/C三档
  - 异议阶段不降价，只讲风险
"""
import os
import sys
import json
import re
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==================== Conversion Score 权重配置 ====================

# state 基础分
_STATE_CONVERSION_WEIGHTS = {
    "NEW": 15,
    "NEEDS_ANALYSIS": 35,
    "BUDGET": 60,
    "OBJECTION": 45,
    "FINAL": 85,
}

# intent 修正
_INTENT_CONVERSION_BONUS = {
    "询价": 5,
    "比价": -5,
    "问工艺": 0,
    "要样品": 5,
    "要目录": 0,
    "问交期": 5,
    "下单": 20,
    "售后": -15,
    "合作": 10,
    "跟进": 0,
}

# price_tier 修正
_TIER_CONVERSION_BONUS = {
    "LOW": -5,
    "MID": 0,
    "HIGH": 10,
    "UNKNOWN": -10,
}

# urgency 对应的动作
_URGENCY_ACTION_MAP = {
    "low": "ask_info",
    "medium": "send_quote",
    "high": "push_close",
}

# ==================== 回复生成提示词 ====================

_REVENUE_PROMPT_TEMPLATE = """你是有15年经验的博汇GLOWFORGE外贸销售 Philip。
你的目标不是回答问题，而是推进成交。

===== 当前客户信息 =====
状态: {state} ({state_label})
价格档位: {price_tier}
成交概率: {conversion_score}/100
客户国家: {country}
客户消息: {message}
意图: {intent}

===== 销售执行指令（必须遵守） =====
{exec_instruction}

===== 回复规则 =====
1. 简短有力，1-3句话，不超过{max_words}个英文单词
2. 不要解释技术参数
3. 不要问客户"Do you have drawings?"或"what size?" — 这些信息收集中拖慢成交
4. 必须带价格锚或A/B/C选择（除非NEW阶段）
5. 直接输出回复文本，不要JSON，不要多余解释
6. 输出只用英文，不需要中文翻译"""


def _calculate_conversion_score(state, intent="", price_tier="UNKNOWN", urgency="low"):
    """计算成交评分 (0-100)

    公式:
      base = state权重
      + intent修正
      + price_tier修正
      + urgency修正
    """
    base = _STATE_CONVERSION_WEIGHTS.get(state, 10)
    intent_bonus = _INTENT_CONVERSION_BONUS.get(intent, 0)
    tier_bonus = _TIER_CONVERSION_BONUS.get(price_tier, -10)

    urgency_bonus = {"low": 0, "medium": 5, "high": 10}.get(urgency, 0)

    score = base + intent_bonus + tier_bonus + urgency_bonus
    return max(0, min(100, score))


def _call_ai(prompt, text, system=None, max_tokens=500, timeout=5):
    """调用 AI 生成回复

    尝试调用 AI API，超时后返回 None 使用 fallback 模板。
    """
    try:
        import requests
        import json
        sys.path.insert(0, BASE_DIR)
        from ai_engine import ALI_KEY, ALI_BASE, TRANSLATE_MODEL
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt + "\n\n" + text})
        payload = {
            "model": TRANSLATE_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        headers = {"Authorization": f"Bearer {ALI_KEY}", "Content-Type": "application/json"}
        r = requests.post(
            f"{ALI_BASE}/chat/completions",
            headers=headers, json=payload, timeout=timeout
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


def _get_fallback_reply(state, price_tier="UNKNOWN"):
    """兜底回复（AI 调用失败时使用模板）"""
    fallbacks = {
        "NEW": (
            "Thanks for reaching out! We specialise in custom LED signage for businesses. "
            "Could you tell me a bit about your store or project? Happy to give you a quick visual preview."
        ),
        "NEEDS_ANALYSIS": (
            "Most of our clients choose between:\n"
            "A) $270 — practical & reliable\n"
            "B) $310 — better visibility at night\n"
            "C) $380 — premium long-term signage\n\n"
            "Which one fits your needs best?"
        ),
        "BUDGET": (
            "Here are the most popular options:\n"
            "A) $270 — standard\n"
            "B) $310 — most popular choice\n"
            "C) $380 — premium with best visibility\n\n"
            "Which tier works for your budget?"
        ),
        "OBJECTION": (
            "I understand price is a concern. Many of our clients initially felt the same.\n"
            "The difference isn't just material — it's how long your sign stays looking great.\n"
            "A $270 sign that lasts 6+ years costs less than a $200 sign replaced every 2 years."
        ),
        "FINAL": (
            "Great choice! We can start production this week if you confirm today.\n"
            "A) $270 — standard production\n"
            "B) $310 — most popular\n"
            "C) $380 — premium with priority\n\n"
            "Which one should I reserve for you?"
        ),
    }
    return fallbacks.get(state, fallbacks["NEEDS_ANALYSIS"])


# ==================== 主引擎 ====================

class RevenueEngine:
    """收单引擎 — 核心 orcherstrator"""

    def __init__(self):
        self._conversion_id = None
        self._process_start = None

    def process(self, message="", intent="", country="", customer_name="", customer_id=0):
        """处理一条客户消息，返回完整的成交动作

        Args:
            message: 客户原始消息
            intent: 已识别的意图（可选）
            country: 国家
            customer_name: 客户名字
            customer_id: 客户 ID（用于 V3 追踪）

        Returns:
            dict: {
                "reply_text": str,          # 发给客户的消息
                "action": str,              # send_quote | ask_info | push_close | reassure | show_case
                "quote_type": str,          # none | simple | ai | formal
                "trigger_whatsapp": bool,   # 是否自动发 WhatsApp
                "urgency": str,             # low | medium | high
                "conversion_score": int,    # 0-100
                "state": str,               # 检测到的状态
                "price_tier": str,          # LOW/MID/HIGH/UNKNOWN
                "deal_probability": float,  # 0-1
                "reason": str,              # 决策原因
                "v3_conversion_id": int,    # V3 追踪 ID
                "v3_ab_version": str,       # A/B 版本
            }
        """
        self._process_start = time.time()

        # ====== 0. V3: A/B 版本选择 ======
        from a_b_optimizer import ABOptimizer
        ab_opt = ABOptimizer()
        ab_version = ab_opt.select_version()

        # ====== 1. 状态检测 ======
        from sales_state import detect_sales_state
        state_info = detect_sales_state(message=message, intent=intent)

        state = state_info["state"]
        price_tier = state_info["price_tier"]
        confidence = state_info["confidence"]

        # ====== 2. 销售行为策略 ======
        from sales_executor import SalesExecutor
        executor = SalesExecutor()
        behavior = executor.execute(state_info, message=message, country=country)

        action = behavior["reply_type"]
        urgency = behavior["urgency_level"]
        quote_trigger = behavior["quote_trigger"]

        # action → whatsapp_action 映射
        action_map = {
            "ask": "ask_info",
            "present_options": "send_quote",
            "anchor_price": "send_quote",
            "handle_objection": "reassure",
            "close": "push_close",
        }
        whatsapp_action = action_map.get(action, "ask_info")

        # ====== 3. Conversion Score ======
        conversion_score = _calculate_conversion_score(state, intent, price_tier, urgency)

        # ====== 4. 报价类型 ======
        quote_type = state_info.get("recommended_quote_type", "none") if quote_trigger else "none"

        # ====== 5. 生成回复 ======
        from sales_state import STATES
        state_label = STATES.get(state, {}).get("label", state)

        # 构建执行指令
        exec_instruction = behavior["sales_instruction"]
        if behavior["requires_risk_framing"]:
            exec_instruction += f"\n\n风险压制话术（必须引用）:\n{behavior['risk_framing']}"

        # V3: 注入 A/B 版本指令
        from a_b_optimizer import ABOptimizer as _ABO
        _abo = _ABO()
        ab_suffix = _abo.get_instruction_suffix(ab_version)
        ab_label = _abo.get_version_label(ab_version)
        exec_instruction += f"\n\n【{ab_label}】\n{ab_suffix}"

        # 构建 AI 提示词
        prompt = _REVENUE_PROMPT_TEMPLATE.format(
            state=state,
            state_label=state_label,
            price_tier=price_tier,
            conversion_score=conversion_score,
            country=country or "unknown",
            message=message,
            intent=intent or "unknown",
            exec_instruction=exec_instruction,
            max_words=behavior.get("max_words", 100),
        )

        # 加载知识库
        try:
            sys.path.insert(0, BASE_DIR)
            from ai_engine import load_knowledge_base
            knowledge_base = load_knowledge_base()
        except Exception:
            knowledge_base = None

        # 调用 AI 生成回复
        reply_text = _call_ai(prompt, message, system=knowledge_base, max_tokens=500, timeout=30)

        # 兜底
        if not reply_text:
            reply_text = _get_fallback_reply(state, price_tier)

        # ====== 6. trigger_whatsapp 决策 ======
        # quote_trigger=True 且 urgency=high/medium → 自动发送
        trigger_whatsapp = quote_trigger and urgency in ("high", "medium")

        # ====== V3: 记录转换 ======
        latency = int((time.time() - self._process_start) * 1000)
        v3_conv_id = 0
        if customer_id > 0:
            try:
                from conversion_tracker import ConversionTracker
                tracker = ConversionTracker()
                v3_conv_id = tracker.record_conversation(
                    customer_id=customer_id,
                    state_info=state_info,
                    behavior={**behavior, "conversion_score": conversion_score},
                    intent=intent,
                    ab_version=ab_version,
                    quote_amount=behavior.get("anchor_price", "0").replace("$", "").replace(",", ""),
                )
                self._conversion_id = v3_conv_id
            except Exception:
                pass

        # ====== 7. 原因说明 ======
        reasons = [f"state:{state}", f"score:{conversion_score}"]
        if price_tier != "UNKNOWN":
            reasons.append(f"tier:{price_tier}")
        if intent:
            reasons.append(f"intent:{intent}")
        reasons.append(f"action:{action}")

        # ====== V4: 更新客户活动状态 ======
        if customer_id > 0:
            try:
                from ai_engine.deal_prioritizer import DealPrioritizer
                DealPrioritizer().update_activity(
                    customer_id=customer_id,
                    state=state,
                    conversion_score=conversion_score,
                    intent=intent,
                )
            except Exception:
                pass

        return {
            "reply_text": reply_text,
            "action": whatsapp_action,
            "quote_type": quote_type,
            "trigger_whatsapp": trigger_whatsapp,
            "urgency": urgency,
            "conversion_score": conversion_score,
            "state": state,
            "price_tier": price_tier,
            "deal_probability": state_info["deal_probability"],
            "recommended_quote_type": state_info["recommended_quote_type"],
            "reason": "; ".join(reasons),
            "v3_conversion_id": v3_conv_id,
            "v3_ab_version": ab_version,
        }

    def close_conversation(self, conversion_id, final_result="won", revenue=0, profit=0, lost_reason=""):
        """关闭一条 V3 转换记录（成交/失败）

        Args:
            conversion_id: v3_conversions ID（来自 process() 输出的 v3_conversion_id）
            final_result: 'won' | 'lost'
            revenue: 成交金额
            profit: 利润
            lost_reason: 失败原因
        """
        try:
            from conversion_tracker import ConversionTracker
            tracker = ConversionTracker()
            tracker.close_conversation(
                conversion_id=conversion_id,
                final_result=final_result,
                revenue=revenue,
                profit=profit,
                lost_reason=lost_reason,
            )
            # 自动触发成交复盘
            try:
                from deal_analyzer import DealAnalyzer
                DealAnalyzer().analyze_conversation(conversion_id)
            except Exception:
                pass
        except Exception:
            pass


# ==================== 快捷入口 ====================

def process_message(message="", intent="", country="", customer_name="", customer_id=0):
    """快捷调用 RevenueEngine"""
    engine = RevenueEngine()
    return engine.process(
        message=message,
        intent=intent,
        country=country,
        customer_name=customer_name,
        customer_id=customer_id,
    )


# ==================== V3 动态权重加载（启动时调用） ====================

def load_v3_optimizations():
    """加载 V3 优化后的权重到内存模块

    在 app.py 启动时调用。
    从 JSON 文件加载优化后的 price anchors 和 intent weights。
    """
    # 加载价格锚
    try:
        from price_optimizer import load_persisted_price_anchors
        load_persisted_price_anchors()
    except Exception:
        pass

    # 加载意图权重
    try:
        from intent_weight_tuner import load_persisted_intent_weights
        load_persisted_intent_weights()
    except Exception:
        pass

    return True
