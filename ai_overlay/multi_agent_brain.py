"""Multi-Agent Sales Brain — 多智能体销售大脑

3个AI角色协同作战:
  1. Sales Closer — 主销售，推进成交
     职责: 逼单、制造紧迫感、引导决策
     路由条件: 成交阶段、高意向客户、OK信号

  2. Technical Advisor — 技术顾问
     职责: 解答技术问题、推荐产品、规格确认
     路由条件: 产品咨询、技术问题、OEM定制

  3. Negotiation Agent — 谈判专家
     职责: 议价、价值锚定、让步策略
     路由条件: 砍价、比价、压价

协作模式:
  - 每个 agent 接收完整上下文但只回应自己负责的部分
  - 可以 handoff: 技术顾问回答完技术问题 → 交还给销售推进
  - 最终输出合并为一个回复
"""
import os
import sys
import logging
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ai_overlay.crm_bridge import get_customer, get_customer_messages, get_products, search_knowledge
from ai_overlay.negotiation import NegotiationAI, is_price_negotiation
from ai_overlay.revenue_pressure import RevenuePressureEngine

logger = logging.getLogger("multi_agent_brain")


# ═══════════════════════════════════════════════════════════
# Agent 1: Sales Closer — 销售关闭专家
# ═══════════════════════════════════════════════════════════

_CLOSING_SCRIPTS = [
    "I can prepare the PI for you right now. Once confirmed, we start production within 24 hours.",
    "Let me send you the proforma invoice — 30% deposit to secure your production slot.",
    "If you confirm today, I can guarantee delivery within [timeframe]. Shall I proceed?",
    "We have a production slot opening this week. Would you like me to reserve it for you?",
    "The price I quoted is valid. Ready to move forward? I'll send the PI immediately.",
]


class SalesCloserAgent:
    """销售关闭专家 — 推进成交"""

    NAME = "Sales Closer"
    ROLE = "销售推进专家"

    @staticmethod
    def handle(customer, state, intent, message_text, history, context=None):
        """销售关闭处理

        参数:
            customer: 客户信息 dict
            state: 当前销售状态
            intent: AI 意图分类
            message_text: 客户最新消息
            history: 消息历史
            context: 额外上下文（可选）

        返回:
            dict: {reply, action, confidence, reason, agent, skip}
        """
        name = customer.get("name", "Customer") if customer else "Customer"
        t = (message_text or "").lower()

        # 1. 客户犹豫 → 用损失厌恶手法
        hesitation = [
            "maybe", "later", "think", "consider", "not sure", "perhaps",
            "i'll let you know", "need time", "再看看", "考虑", "想一下",
            "考虑考虑", "在看看",
        ]
        if any(h in t for h in hesitation):
            return {
                "reply": (
                    f"I understand you want to think it over, {name}. "
                    f"Just to let you know, our current production slot is filling up fast. "
                    f"Early confirmation not only secures your delivery date but also locks in "
                    f"the current price. Should I go ahead and prepare the PI for you?"
                ),
                "action": "close",
                "confidence": 0.75,
                "reason": "客户犹豫，用损失厌恶手法推进",
                "agent": "closer",
            }

        # 2. 客户明确表示购买意向 → 直接发PI
        buying_signals = [
            "yes", "ok", "deal", "agree", "send", "proceed", "i want",
            "i'll take", "place order", "下单", "可以", "好的", "合同",
            "来做", "确认订单",
        ]
        if any(b in t for b in buying_signals):
            return {
                "reply": (
                    f"Great decision, {name}! I'll prepare the PI right away. "
                    f"Here's what I need from you:\n"
                    f"1. Confirmed product specifications\n"
                    f"2. Shipping address\n"
                    f"3. Preferred payment method (TT / Western Union)\n\n"
                    f"Once I have these, I'll send the PI within minutes!"
                ),
                "action": "close",
                "confidence": 0.95,
                "reason": "客户确认购买，收集信息发PI",
                "agent": "closer",
            }

        # 3. 客户问具体价格但未给规格 → 引导给规格
        price_intent = any(w in t for w in [
            "how much", "price", "cost", "quote", "多少钱",
            "报价", "什么价", "怎么卖",
        ])
        has_specs = any(s in t for s in [
            "cm", "mm", "m", "meter", "size", "×", "米",
        ])
        if price_intent and not has_specs:
            return {
                "reply": (
                    f"Thanks for your interest, {name}! The price depends on "
                    f"the size and quantity. Could you let me know:\n"
                    f"• What size sign do you need?\n"
                    f"• How many pieces?\n"
                    f"• Indoor or outdoor use?\n\n"
                    f"With these details, I can give you an accurate quote right away."
                ),
                "action": "reply",
                "confidence": 0.80,
                "reason": "客户询价但缺规格，引导客户提供信息",
                "agent": "closer",
            }

        # 4. 常规推进 — 根据状态选择话术
        state_scripts = {
            "NEW": f"Thanks for reaching out, {name}! We're a professional signage manufacturer. "
                   f"What kind of sign are you looking for?",
            "QUALIFYING": f"Great, {name}! To help you better, could you tell me more about "
                          f"your specific requirements? Size, quantity, and installation location?",
            "PRICING": f"{name}, I'd love to move forward with you. Do you have any questions "
                       f"about the pricing or specifications?",
            "NEGOTIATING": f"{name}, I want to make this work for you. Let me know what would "
                           f"help you make a decision today.",
            "FOLLOWUP": f"Hi {name}, just checking in. Any updates on your end? "
                        f"Happy to help if you need anything!",
            "COLD": f"Hi {name}, it's been a while! We have some new products that might interest you.",
        }

        script = state_scripts.get(state, f"Hi {name}, how can I help you today?")
        return {
            "reply": script,
            "action": "reply",
            "confidence": 0.70,
            "reason": f"常规推进 (state={state})",
            "agent": "closer",
        }


# ═══════════════════════════════════════════════════════════
# Agent 2: Technical Advisor — 技术顾问
# ═══════════════════════════════════════════════════════════

_MATERIAL_ADVICE = {
    "outdoor": (
        "For outdoor use, I recommend stainless steel (SUS304) with acrylic face — "
        "it's rust-proof and weather-resistant. Very popular for storefront signs."
    ),
    "indoor": (
        "For indoor use, acrylic with LED backlight is the most cost-effective choice. "
        "Lightweight and looks premium."
    ),
    "premium": (
        "Our premium option is CNC-machined solid brass with mirror finish — "
        "very high-end look for luxury brands and hotels."
    ),
    "budget": (
        "Our acrylic LED sign is the most popular budget-friendly option. "
        "Still looks great and lasts 3-5 years with normal use."
    ),
}


class TechnicalAdvisorAgent:
    """技术顾问 — 产品/技术解答"""

    NAME = "Technical Advisor"
    ROLE = "技术顾问"

    @staticmethod
    def handle(customer, state, intent, message_text, history, context=None):
        """技术问题解答

        返回:
            dict: {reply, action, confidence, reason, agent, skip}
        """
        name = customer.get("name", "Customer") if customer else "Customer"
        t = (message_text or "").lower()

        # 搜索知识库
        knowledge = search_knowledge(message_text, limit=2)

        # 1. 材质咨询
        if any(w in t for w in [
            "material", "stainless", "acrylic", "metal", "材质",
            "不锈钢", "亚克力", "什么材料",
        ]):
            outdoor = any(w in t for w in ["outdoor", "outside", "weather", "户外", "室外"])
            premium = any(w in t for w in ["premium", "high-end", "luxury", "高端", "豪华"])
            budget = any(w in t for w in ["cheap", "budget", "affordable", "便宜", "预算"])

            if premium:
                advice = _MATERIAL_ADVICE["premium"]
            elif outdoor:
                advice = _MATERIAL_ADVICE["outdoor"]
            elif budget:
                advice = _MATERIAL_ADVICE["budget"]
            else:
                advice = _MATERIAL_ADVICE["indoor"]

            return {
                "reply": f"Great question about materials, {name}! {advice}",
                "action": "reply",
                "confidence": 0.85,
                "reason": "材质技术解答",
                "agent": "technical",
            }

        # 2. 尺寸/规格咨询
        if any(w in t for w in [
            "size", "dimension", "measure", "how big",
            "尺寸", "多大", "规格", "做多大",
        ]):
            return {
                "reply": (
                    f"We offer fully customized sizes, {name}! From small 20cm letters "
                    f"to large 5m+ building signs. The size depends on where you're installing it. "
                    f"For a typical storefront, 1.2m to 2m wide works well. "
                    f"What's your installation space?"
                ),
                "action": "reply",
                "confidence": 0.80,
                "reason": "尺寸技术解答",
                "agent": "technical",
            }

        # 3. OEM/定制咨询
        if any(w in t for w in [
            "oem", "custom", "logo", "design", "定制", "OEM",
            "logo", "自己的", "设计",
        ]):
            return {
                "reply": (
                    f"Absolutely, {name}! We specialize in OEM/ODM orders. "
                    f"Here's the process:\n"
                    f"1. Send us your design/logo file (AI, PDF, or CAD)\n"
                    f"2. We provide a free proof within 24 hours\n"
                    f"3. You approve → we start production\n\n"
                    f"No design? We have in-house designers who can create one for you!"
                ),
                "action": "reply",
                "confidence": 0.90,
                "reason": "OEM定制解答",
                "agent": "technical",
            }

        # 4. 样品咨询
        if any(w in t for w in ["sample", "样品", "样板"]):
            return {
                "reply": (
                    f"Yes, we can provide samples, {name}! Here's our sample policy:\n"
                    f"• Sample cost is required (refundable upon bulk order)\n"
                    f"• Production time: 3-5 working days\n"
                    f"• We ship via DHL/UPS/FedEx\n\n"
                    f"Let me know the details and I'll prepare a sample for you!"
                ),
                "action": "reply",
                "confidence": 0.85,
                "reason": "样品咨询解答",
                "agent": "technical",
            }

        # 5. 物流/交期咨询
        if any(w in t for w in [
            "ship", "delivery", "shipping", "logistics", "freight",
            "物流", "运费", "海运", "空运", "发货", "交期",
        ]):
            return {
                "reply": (
                    f"Here's our shipping info, {name}:\n"
                    f"• We ship worldwide via sea or air\n"
                    f"• Typical delivery: 10-15 working days after deposit\n"
                    f"• FOB Shenzhen or CIF to your port\n"
                    f"• We handle all customs documentation\n\n"
                    f"For urgent orders, we offer express production (5-7 days)."
                ),
                "action": "reply",
                "confidence": 0.80,
                "reason": "物流交期解答",
                "agent": "technical",
            }

        # 6. 质量/认证咨询
        if any(w in t for w in [
            "quality", "certification", "warranty", "guarantee", "ce",
            "rohs", "iso", "质量", "认证", "质保", "保修",
        ]):
            return {
                "reply": (
                    f"Quality is our top priority, {name}! Here's what sets us apart:\n"
                    f"• CE, ROHS, and ISO certified\n"
                    f"• Export-grade LED beads (50,000+ hours lifespan)\n"
                    f"• SUS304 stainless steel (no rust, no fade)\n"
                    f"• 2-year warranty on all products\n"
                    f"• 3 quality inspections before shipping"
                ),
                "action": "reply",
                "confidence": 0.90,
                "reason": "质量认证解答",
                "agent": "technical",
            }

        # 7. 非技术问题 → 跳过（让其他 agent 处理）
        return {
            "reply": None,
            "action": None,
            "confidence": 0,
            "reason": "非技术问题，跳过",
            "agent": "technical",
            "skip": True,
        }


# ═══════════════════════════════════════════════════════════
# Agent 3: Negotiation Agent — 谈判专家
# ═══════════════════════════════════════════════════════════

_COMPARISON_SCRIPTS = [
    (
        "I understand you're comparing options. Here's what makes us different:\n"
        "• We manufacture directly — no middleman markup\n"
        "• Export-grade materials with 2-year warranty\n"
        "• Custom design service included\n"
        "• 500+ signs produced monthly — proven quality\n\n"
        "Price is important, but value matters more. Let me show you our quality firsthand."
    ),
    (
        "I get it — you want the best value. Let me share why our clients choose us:\n"
        "• Factory-direct pricing — 30-40% less than trading companies\n"
        "• Premium materials that last 5+ years\n"
        "• Free artwork proof within 24 hours\n"
        "• Full after-sales support\n\n"
        "If another supplier offers a lower price, I'd be happy to match or beat it — "
        "just send me their quote!"
    ),
]

_DISCOUNT_SCRIPTS = {
    "first_order": (
        "As a gesture for first-time cooperation, I can offer you a special discount. "
        "This is our best price — let me send you the PI to lock it in."
    ),
    "volume": (
        "For bulk orders, we can definitely work on the pricing. "
        "What quantity are you looking at? The more you order, the better the unit price."
    ),
    "firm": (
        "I appreciate your budget concern, but this price already reflects our "
        "factory-direct policy. Instead of reducing quality, I can recommend a "
        "slightly smaller size to fit your budget."
    ),
}


class NegotiationAgent:
    """谈判专家 — 议价/比价/压价处理"""

    NAME = "Negotiation Agent"
    ROLE = "谈判专家"

    @staticmethod
    def handle(customer, state, intent, message_text, history, context=None):
        """议价处理

        返回:
            dict: {reply, action, confidence, reason, agent, skip, ...}
        """
        customer_value = (context or {}).get("customer_value", 50)
        margin_safe = (context or {}).get("margin_safe", True)
        t = (message_text or "").lower()

        # 1. 比价处理
        comparison_keywords = [
            "other supplier", "other company", "competitor", "另一家",
            "别家", "其他家", "竞争对手", "人家",
        ]
        if any(k in t for k in comparison_keywords):
            script = random.choice(_COMPARISON_SCRIPTS)
            # 高价值客户 → 同意比价
            if customer_value >= 60:
                return {
                    "reply": script,
                    "action": "reply",
                    "confidence": 0.80,
                    "reason": "客户在比价，用工厂直销优势回应",
                    "agent": "negotiator",
                }
            # 一般客户 → 强调质量
            return {
                "reply": (
                    f"I understand you're shopping around. What I can tell you is that "
                    f"we use genuine export-grade materials with full certification. "
                    f"Lower prices usually mean lower quality — thinner material, "
                    f"cheaper LED beads, shorter lifespan. \n\n"
                    f"Our price reflects real quality that lasts."
                ),
                "action": "reply",
                "confidence": 0.75,
                "reason": "客户比价，用质量差异说服",
                "agent": "negotiator",
            }

        # 2. 砍价处理（复用 V1.2 NegotiationAI）
        if is_price_negotiation(message_text):
            ai_result = NegotiationAI.decide(message_text, customer_value, margin_safe)

            if ai_result:
                strategy = ai_result.get("strategy")

                # 小让步 + 价值锚定
                if strategy == "small_concession" and margin_safe:
                    reply = _DISCOUNT_SCRIPTS["first_order"]
                elif strategy == "value_shift":
                    reply = _DISCOUNT_SCRIPTS["firm"]
                elif strategy == "firm":
                    reply = _DISCOUNT_SCRIPTS["firm"]
                else:
                    reply = ai_result.get("reply", _DISCOUNT_SCRIPTS["firm"])

                return {
                    "reply": reply,
                    "action": "reply",
                    "confidence": 0.85,
                    "reason": ai_result.get("reasoning", "议价处理"),
                    "agent": "negotiator",
                    "strategy": strategy,
                    "discount_allowed": ai_result.get("discount_allowed", 0),
                }

            # 检测到砍价信号但 NegotiationAI 没有决策
            return {
                "reply": (
                    f"I understand price is important. Let me explain what makes "
                    f"our quality different — we use certified materials and all "
                    f"products come with warranty. The price reflects real value."
                ),
                "action": "reply",
                "confidence": 0.70,
                "reason": "砍价信号检测但无明确决策，用价值锚定回应",
                "agent": "negotiator",
            }

        # 3. 无砍价/比价信号 → 跳过
        return {
            "reply": None,
            "action": None,
            "confidence": 0,
            "reason": "无砍价/比价信号，跳过",
            "agent": "negotiator",
            "skip": True,
        }


# ═══════════════════════════════════════════════════════════
# 路由引擎
# ═══════════════════════════════════════════════════════════

AGENT_REGISTRY = {
    "closer": SalesCloserAgent(),
    "technical": TechnicalAdvisorAgent(),
    "negotiator": NegotiationAgent(),
}

# 意图到 Agent 的映射
_INTENT_ROUTE = {
    "pricing": "closer",
    "ready_to_order": "closer",
    "bargaining": "negotiator",
    "complaint": "closer",
    "sample_request": "technical",
    "oem_inquiry": "technical",
    "shipping_inquiry": "technical",
    "product_inquiry": "technical",
}

# 状态到 Agent 的映射（作为意图映射的 fallback）
_STATE_ROUTE = {
    "NEW": "closer",
    "QUALIFYING": "closer",
    "PRICING": "closer",
    "NEGOTIATING": "negotiator",
    "CLOSING": "closer",
    "HOT": "closer",
    "FOLLOWUP": "closer",
    "COLD": "closer",
}


class MultiAgentRouter:
    """多智能体路由器 — 决定哪个 agent 处理当前消息"""

    @staticmethod
    def route(customer, state, intent, message_text, history, context=None):
        """路由到合适的 agent(s) 并获取回复

        可能多个 agent 协同工作:
          - 主要 agent 生成主回复
          - 辅助 agent 补充信息

        参数:
            customer: 客户信息 dict
            state: 当前销售状态
            intent: AI 意图分类
            message_text: 客户最新消息
            history: 消息历史
            context: 额外上下文字典（可选，含 customer_value, margin_safe 等）

        返回:
            dict: {
                primary_agent: str,
                reply: str or None,
                confidence: float,
                agents_used: [str],
                handoff_suggested: bool,
                details: dict
            }
        """
        # 1. 确定主要 agent
        primary = _INTENT_ROUTE.get(intent) or _STATE_ROUTE.get(state, "closer")

        # 2. 确定辅助 agent（如果场景需要协同）
        secondary = None
        if primary == "closer" and intent == "product_inquiry":
            secondary = "technical"
        elif primary == "technical" and state in ("PRICING", "NEGOTIATING"):
            secondary = "closer"
        elif primary == "closer" and intent == "bargaining":
            secondary = "negotiator"
        elif primary == "negotiator" and state in ("NEW", "QUALIFYING"):
            secondary = "closer"

        # 3. 处理主要 agent
        primary_agent = AGENT_REGISTRY.get(primary)
        if not primary_agent:
            return {
                "primary_agent": "closer",
                "reply": None,
                "confidence": 0.5,
                "agents_used": [],
                "handoff_suggested": False,
                "details": {"reason": f"未知 agent: {primary}, 使用 closer fallback"},
            }

        primary_result = primary_agent.handle(
            customer, state, intent, message_text, history, context
        )

        # 4. 处理辅助 agent（如果需要）
        secondary_result = None
        if secondary:
            sec_agent = AGENT_REGISTRY.get(secondary)
            if sec_agent:
                secondary_result = sec_agent.handle(
                    customer, state, intent, message_text, history, context
                )

        # 5. 合并回复
        combined_reply = primary_result.get("reply") or ""
        needs_handoff = False

        if secondary_result and not secondary_result.get("skip"):
            sec_reply = secondary_result.get("reply") or ""
            if sec_reply and sec_reply != combined_reply:
                combined_reply = sec_reply + "\n\n" + combined_reply
                needs_handoff = True

        # 6. 如果主要 agent 跳过了但有辅助结果 → 用辅助的
        if primary_result.get("skip") and secondary_result and not secondary_result.get("skip"):
            combined_reply = secondary_result.get("reply", "")
            primary = secondary or primary
            primary_result = secondary_result

        # 7. 如果所有 agent 都跳过 → 返回 None
        if not combined_reply:
            return {
                "primary_agent": primary,
                "reply": None,
                "confidence": 0.5,
                "agents_used": [primary],
                "handoff_suggested": False,
                "details": {"reason": "所有 agent 跳过，需要 fallback 处理"},
            }

        return {
            "primary_agent": primary,
            "reply": combined_reply,
            "confidence": primary_result.get("confidence", 0.7),
            "agents_used": list(dict.fromkeys([p for p in [primary, secondary] if p])),
            "handoff_suggested": needs_handoff,
            "details": {
                "primary_reason": primary_result.get("reason", ""),
                "secondary_reason": secondary_result.get("reason", "") if secondary_result else None,
            },
        }

    @staticmethod
    def route_by_agent_name(customer, state, intent, message_text, history, agent_name, context=None):
        """直接指定 agent 处理（用于测试/特定场景）"""
        agent = AGENT_REGISTRY.get(agent_name)
        if not agent:
            return {"error": f"未知 agent: {agent_name}"}
        return agent.handle(customer, state, intent, message_text, history, context)


# ── 快捷函数 ──────────────────────────────────────────────

def list_agents():
    """列出所有可用 agent 及其能力"""
    return [
        {"name": "closer", "role": SalesCloserAgent.ROLE},
        {"name": "technical", "role": TechnicalAdvisorAgent.ROLE},
        {"name": "negotiator", "role": NegotiationAgent.ROLE},
    ]
