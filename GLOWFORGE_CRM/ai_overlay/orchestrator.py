"""Orchestrator — 销售推进引擎

职责:
  1. 评估客户在销售周期中的位置
  2. 决定下一步动作（推进成交）
  3. 生成回复或调度操作

这不是规则引擎，这是「销售推进系统」。
"""
import os
import sys
import json
import time
import logging

# 确保可引用 CRM 根目录的模块
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ai_overlay.crm_bridge import (
    get_customer, get_customer_messages, get_products,
    search_knowledge, get_lead_state, save_quote, send_whatsapp
)
from ai_overlay.stabilization import (
    StateSyncEngine, ConversationLock, ConfidenceGate, FollowUpGuard, stabilize
)
from ai_overlay.lead_scoring import LeadScorer
from ai_overlay.negotiation import NegotiationAI, is_price_negotiation
from ai_overlay.campaign import CampaignEngine
from ai_overlay.sales_autopilot import SalesAutopilot
from ai_overlay.proactive_messaging import ProactiveMessagingEngine
from ai_overlay.conversion_decision import ConversionDecisionEngine
from ai_overlay.revenue_pressure import RevenuePressureEngine
from ai_overlay.multi_agent_brain import MultiAgentRouter

logger = logging.getLogger("orchestrator")

# ── 销售状态定义（映射到 CRM lead_state + 补充说明） ─────

SALES_STATES = {
    "NEW":              "首次接触，需要了解客户需求",
    "QUALIFYING":       "正在确认规格/数量/预算",
    "PRICING":          "已报价或正在讨论价格",
    "NEGOTIATING":      "客户在比价/压价/犹豫",
    "CLOSING":          "准备成交，推进定金",
    "FOLLOWUP":         "等待客户回复中",
    "COLD":             "长时间无回应",
    "ESCALATED":        "已转人工",
    "CLOSED_WON":       "已成交",
    "CLOSED_LOST":      "已丢失",
}

# ── 辅助: 判定客户紧迫度 ────────────────────────────────

_URGENCY_KEYWORDS = {
    "high": ["urgent", "asap", "quick", "fast", "need it", "rush", "emergency",
             "today", "this week", "hurry", "马上", "急", "尽快", "加急"],
    "medium": ["soon", "next week", "this month", "looking for", "considering",
               "打算", "考虑", "想买"],
    "low": ["just looking", "browsing", "maybe", "sometime", "future",
            "看看", "随便", "以后", "了解"],
}


def _detect_urgency(text):
    text = (text or "").lower()
    for level, keywords in _URGENCY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return level
    return "medium"


# ── 辅助: 判定客户价值 ──────────────────────────────────

def _estimate_value(customer, products_of_interest=None):
    """基于客户信息和产品兴趣估算潜在价值"""
    score = 0
    country = (customer.get("country") or "").upper()
    # 高价值市场
    if country in ("US", "GB", "DE", "FR", "AU", "CA", "AE", "SA", "JP"):
        score += 30
    elif country in ("ES", "IT", "NL", "SG", "MY", "KR", "NZ"):
        score += 20
    elif country:
        score += 10
    # 已有分级
    ls = customer.get("lead_score", 0) or 0
    score += min(ls, 40)
    return min(score, 100)


# ── 核心: 销售推进决策 ──────────────────────────────────

def decide(customer_id, message_text, extra_context=None):
    """主入口：分析客户消息并决定销售推进动作

    参数:
        customer_id: CRM 客户 ID
        message_text: 客户最新消息原文
        extra_context: 可选额外上下文

    返回:
        dict: {
            state: 当前销售状态
            action: 决定动作 (reply/quote/escalate/followup/wait)
            confidence: 信心分 0-100
            reply: 建议回复内容
            reason: 决策理由
        }
    """
    ctx = extra_context or {}

    # 1. 获取客户全貌
    customer = get_customer(customer_id)
    if not customer:
        return {"error": "customer_not_found", "action": "error"}

    lead_state = get_lead_state(customer_id)
    current_state = lead_state.get("lead_state", "NEW")
    history = get_customer_messages(customer_id, limit=10)

    # 2. 评估
    urgency = _detect_urgency(message_text)
    value = _estimate_value(customer)
    intent = ctx.get("intent") or _classify_intent(message_text)

    # 3. Lead Scoring 2.0: 成交概率评分
    scoring = LeadScorer.score(customer_id)
    score_tier = scoring.get("tier", "COLD")
    score_val = scoring.get("score", 0)

    # 4. [V1.3] Multi-Agent Brain: 多智能体销售大脑
    agent_context = {"customer_value": value, "margin_safe": ctx.get("margin_safe", True)}
    agent_result = MultiAgentRouter.route(
        customer, current_state, intent, message_text, history, agent_context
    )

    # 5. [V1.3] Sales Autopilot: 强制状态推进检查
    autopilot = SalesAutopilot.evaluate(
        customer_id, current_state, intent, message_text, history
    )

    # 6. [V1.3] Conversion Decision: 成交时机判断
    conversion = ConversionDecisionEngine.evaluate(
        customer_id, score_val, current_state, message_text, history
    )

    # 7. Negotiation AI: 检测砍价
    negotiation = None
    if is_price_negotiation(message_text) or intent == "bargaining":
        margin_safe = ctx.get("margin_safe", True)
        negotiation = NegotiationAI.decide(message_text, value, margin_safe=margin_safe)

    # 8. 状态感知决策
    decision = _route_decision(
        state=current_state,
        intent=intent,
        urgency=urgency,
        value=value,
        history_count=len(history),
        message=message_text,
        customer=customer,
        tier=score_tier,
    )

    # 9. 决策覆盖: Sales Autopilot + Conversion Decision 影响
    # V1.3 Autopilot: 如果需要强制推进，覆盖 next_state
    if autopilot.get("force_progression") and autopilot.get("proposed_state"):
        decision["next_state"] = autopilot["proposed_state"]
        decision["reason"] += f" | Autopilot: {autopilot['reason']}"
        # 如果推进到 CLOSING，同时提升动作
        if autopilot["proposed_state"] == "CLOSING":
            decision["action"] = "escalate"
            decision["confidence"] = max(decision.get("confidence", 50), 85)
            decision["suggested_priority"] = "high"

    # V1.3 Conversion Decision: 如果检测到强成交信号，提升动作
    if conversion.get("should_close"):
        if decision["action"] not in ("escalate",):
            decision["action"] = "quote"
            decision["confidence"] = max(decision.get("confidence", 50), 80)
            decision["reason"] += f" | ConversionDecision: {conversion['reason']}"
            decision["close_score"] = conversion.get("close_score")
            decision["close_method"] = conversion.get("method")

    # 10. 如果决定回复，生成回复内容
    if decision["action"] in ("reply", "quote"):
        # V1.3: 优先使用 multi-agent 回复
        if agent_result and agent_result.get("reply"):
            reply = agent_result["reply"]
        else:
            reply = _generate_reply(
                customer=customer,
                state=current_state,
                intent=intent,
                message=message_text,
                decision=decision,
                history=history,
            )
        # 如果有 Negotiation AI 建议，覆盖回复
        if negotiation and negotiation.get("reply"):
            reply = negotiation["reply"]

        # V1.3 Proactive Messaging: 追加主动追问
        reply = ProactiveMessagingEngine.get_combined_reply(
            reply, customer, current_state, intent, history, message_text
        )

        # V1.3 Revenue Pressure: 追加紧迫感
        pressure_tier = RevenuePressureEngine.select_tier(
            decision.get("next_state", current_state), score_val
        )
        reply = RevenuePressureEngine.append_to_reply(
            reply, pressure_tier, customer.get("name", "Customer")
        )

        decision["reply"] = reply

    # 11. 通过稳定层: 状态同步 + 置信度门控
    ConversationLock.record_message(customer_id, direction="received")
    proposed_state = decision.get("next_state")

    # 评分影响置信度: HOT客户提高下限
    base_confidence = decision.get("confidence", 50)
    if score_tier == "HOT":
        base_confidence = max(base_confidence, 70)
    elif score_tier == "COLD":
        base_confidence = min(base_confidence, 40)
    confidence = base_confidence / 100.0

    st = stabilize({
        "customer_id": customer_id,
        "crm_state": current_state,
        "ai_proposed_state": proposed_state,
        "confidence": confidence,
        "action": decision["action"],
        "reply": decision.get("reply", ""),
    })

    # 12. 组装最终输出
    result = {
        "customer_id": customer_id,
        "state": st["state"],
        "state_changed": st["state_changed"],
        "intent": intent,
        "action": st["action"],
        "confidence": st["confidence"],
        "urgency": urgency,
        "value_score": value,
        "lead_score": score_val,
        "lead_tier": score_tier,
        "reply": st["reply"],
        "safe_to_execute": st["safe_to_execute"],
        "execution_level": st["execution_level"],
        "conversation_locked": st["conversation_locked"],
        "warnings": st["warnings"],
        "gate_reason": st["gate_reason"],
        "negotiation": negotiation,
        # V1.3 新增字段
        "agent_used": agent_result.get("primary_agent") if agent_result else None,
        "agents_used": agent_result.get("agents_used", []) if agent_result else [],
        "autopilot_forced": autopilot.get("force_progression", False),
        "autopilot_strategy": autopilot.get("strategy"),
        "close_ready": conversion.get("should_close", False),
        "close_score": conversion.get("close_score"),
        "close_method": conversion.get("method"),
        "proactive_applied": bool(
            agent_result and agent_result.get("reply")
            and ProactiveMessagingEngine.should_be_proactive(
                customer, current_state, intent, history, message_text
            ).get("should")
        ),
    }

    logger.info(
        f"[{customer_id}] state={current_state}→{st['state']} "
        f"intent={intent} action={result['action']} "
        f"confidence={result['confidence']} safe={result['safe_to_execute']}"
    )
    return result


# ── 意图分类（轻量版，复用 CRM 的 AI 或本地规则） ──────

def _classify_intent(text):
    """快速意图分类，规则+AI混合"""
    t = (text or "").lower()

    # 规则匹配（常见模式走快速通道）
    price_words = ["how much", "price", "cost", "quote", "quotation", "pricing",
                   "多少钱", "报价", "价格", "什么价", "怎么卖"]
    product_words = ["what", "which", "product", "model", "have", "sell",
                     "什么", "产品", "型号", "有"]
    order_words = ["order", "buy", "purchase", "place", "下单", "买", "订"]
    sample_words = ["sample", "样品", "样板", "打样"]
    shipping_words = ["ship", "delivery", "shipping", "logistics", " freight",
                      "物流", "运费", "海运", "空运", "发货", "交期"]
    complaint_words = ["bad", "broken", "damage", "complaint", "wrong",
                       "质量", "坏了", "破损", "投诉", "不对"]
    oem_words = ["custom", "oem", "logo", "brand", "定制", "OEM", "logo"]
    bargaining_words = ["expensive", "cheap", "too much", "discount", "better price",
                        "贵", "太贵", "便宜", "打折", "优惠"]

    if any(w in t for w in bargaining_words):
        return "bargaining"
    if any(w in t for w in price_words):
        return "pricing"
    if any(w in t for w in order_words):
        return "ready_to_order"
    if any(w in t for w in sample_words):
        return "sample_request"
    if any(w in t for w in complaint_words):
        return "complaint"
    if any(w in t for w in oem_words):
        return "oem_inquiry"
    if any(w in t for w in shipping_words):
        return "shipping_inquiry"
    if any(w in t for w in product_words):
        return "product_inquiry"
    return "general"


# ── 路由决策 ────────────────────────────────────────────

def _route_decision(state, intent, urgency, value, history_count, message, customer, tier=None):
    """根据当前状态+意图，决定下一步动作"""

    # --- 高价值客户/投诉 → 立即转人工 ---
    if intent == "complaint":
        return {
            "action": "escalate",
            "confidence": 90,
            "reason": "投诉/负面情绪，需要人工处理",
            "suggested_priority": "high",
        }

    # --- NEW: 首次接触 ---
    if state == "NEW":
        if intent in ("pricing", "product_inquiry"):
            return {
                "action": "reply",
                "confidence": 85,
                "reason": "新客户有明确需求，先了解规格再报价",
                "next_state": "QUALIFYING",
            }
        return {
            "action": "reply",
            "confidence": 70,
            "reason": "新客户，先打招呼了解需求",
            "next_state": "QUALIFYING",
        }

    # --- QUALIFYING: 了解需求中 ---
    if state == "QUALIFYING":
        if intent in ("pricing", "ready_to_order"):
            return {
                "action": "quote",
                "confidence": 80,
                "reason": "客户已表示要价格/下单，生成报价",
                "next_state": "PRICING",
            }
        return {
            "action": "reply",
            "confidence": 75,
            "reason": "继续追问规格细节以推进",
            "next_state": "QUALIFYING",
        }

    # --- PRICING: 已报价或正谈价格 ---
    if state == "PRICING":
        if intent == "bargaining":
            return {
                "action": "reply",
                "confidence": 85,
                "reason": "客户在压价，启动价值锚定话术",
                "next_state": "NEGOTIATING",
            }
        if intent == "ready_to_order":
            return {
                "action": "escalate",
                "confidence": 90,
                "reason": "客户确认要下单，通知销售跟进",
                "next_state": "CLOSING",
                "suggested_priority": "high",
            }
        if urgency == "high":
            return {
                "action": "quote",
                "confidence": 75,
                "reason": "客户急迫，再次推进报价",
                "next_state": "PRICING",
            }
        return {
            "action": "reply",
            "confidence": 65,
            "reason": "继续保持对话，回答客户疑问",
            "next_state": "PRICING",
        }

    # --- NEGOTIATING: 压价/犹豫中 ---
    if state == "NEGOTIATING":
        if value >= 70:
            return {
                "action": "escalate",
                "confidence": 80,
                "reason": f"高价值客户({value}分)在犹豫，人工介入提高转化",
                "suggested_priority": "high",
            }
        return {
            "action": "reply",
            "confidence": 75,
            "reason": "标准压价处理，用价值锚定+ABC选择法",
            "next_state": "NEGOTIATING",
        }

    # --- CLOSING: 准备成交 ---
    if state == "CLOSING":
        return {
            "action": "escalate",
            "confidence": 95,
            "reason": "客户准备成交，需要人工处理收款",
            "suggested_priority": "high",
        }

    # --- FOLLOWUP: 等待回复中 ---
    if state in ("FOLLOWUP", "COLD"):
        return {
            "action": "reply",
            "confidence": 60,
            "reason": "唤醒客户，轻量跟进",
            "next_state": "QUALIFYING",
        }

    # --- 默认 ---
    return {
        "action": "reply",
        "confidence": 50,
        "reason": "常规回复",
        "next_state": state,
    }


# ── 回复生成 ────────────────────────────────────────────

def _generate_reply(customer, state, intent, message, decision, history):
    """基于销售策略生成回复内容

    使用现有 CRM 的 AI 引擎生成回复，如果不可用则用模板。
    """
    customer_name = customer.get("name", "Customer")

    # 尝试用 CRM 的 AI 引擎
    try:
        from ai_engine import analyze_customer_message
        # 构造历史供 AI 参考
        history_for_ai = []
        for m in history[-6:]:
            history_for_ai.append({
                "role": m.get("direction", "received"),
                "content_cn": m.get("content_cn", ""),
                "content_en": m.get("content_en", ""),
            })
        analysis = analyze_customer_message(
            text=message,
            country=customer.get("country", ""),
            history=history_for_ai,
            sales_name="Philip",
            customer_id=customer.get("id", 0),
        )
        if analysis and not analysis.get("error"):
            return analysis.get("suggested_reply_en", "")
    except Exception:
        pass

    # 降级：模板回复
    templates = {
        "pricing": (
            f"Thanks for your interest! To give you an accurate price, "
            f"could you let me know the quantity and size you need?"
        ),
        "product_inquiry": (
            f"Great choice! We have several options available. "
            f"Could you tell me more about your specific requirements?"
        ),
        "bargaining": (
            f"I understand price is important. Let me show you "
            f"what makes our quality different — we use certified materials "
            f"and all our products come with warranty."
        ),
        "ready_to_order": (
            f"Perfect! Let me prepare the invoice for you. "
            f"I'll send the PI with our payment terms shortly."
        ),
        "sample_request": (
            f"Yes, we can provide samples. There's a sample cost "
            f"which is refundable upon bulk order. Let me know the details."
        ),
        "shipping_inquiry": (
            f"We ship worldwide via sea/air. Typical delivery time is "
            f"10-15 working days after deposit. FOB Shenzhen or CIF available."
        ),
        "complaint": (
            f"I'm sorry to hear that. Let me take care of this for you. "
            f"Could you send me a photo so I can check immediately?"
        ),
        "oem_inquiry": (
            f"Yes, we support OEM/custom orders. We can work with your "
            f"design or create one for you. What specifications do you have?"
        ),
        "general": (
            f"Thanks for reaching out! We're a professional signage "
            f"manufacturer based in Zhongshan, China. How can I help you today?"
        ),
    }
    return templates.get(intent, templates["general"])


# ── 快捷入口 ────────────────────────────────────────────

def process_message(customer_id, message_text, extra_context=None):
    """一站式处理客户消息：分析→决策→稳定层校验→生成回复

    返回:
        dict: {reply, action, safe_to_execute, state, confidence, warnings}
    """
    result = decide(customer_id, message_text, extra_context)

    # 不安全操作（置信度不足或被锁定）只建议不执行
    if not result.get("safe_to_execute", True):
        logger.warning(
            f"[Gate] 客户#{customer_id} 操作被阻止: "
            f"action={result.get('action')} "
            f"confidence={result.get('confidence')} "
            f"locked={result.get('conversation_locked')}"
        )
        return {
            "reply": result.get("reply", ""),
            "action": "advisory_only",
            "safe_to_execute": False,
            "state": result.get("state"),
            "confidence": result.get("confidence"),
            "warnings": result.get("warnings", []),
        }

    if result.get("action") == "escalate":
        return {
            "reply": "Let me connect you with our sales manager who will assist you shortly.",
            "action": "escalate",
            "state": result.get("state"),
            "priority": result.get("suggested_priority", "normal"),
        }

    if result.get("action") == "quote":
        try:
            qr = save_quote({
                "clientId": customer_id,
                "productLabel": "LED Sign",
                "totalQty": 1,
                "formalTotal": "0",
            })
            quote_msg = "\n\nI've prepared a quotation for you. Let me know if you have any questions."
            reply = (result.get("reply") or "") + quote_msg
        except Exception:
            reply = result.get("reply", "")
        return {"reply": reply, "action": "quote", "state": result.get("state")}

    return {
        "reply": result.get("reply", ""),
        "action": result.get("action", "reply"),
        "state": result.get("state"),
        "confidence": result.get("confidence"),
        "safe_to_execute": True,
    }
