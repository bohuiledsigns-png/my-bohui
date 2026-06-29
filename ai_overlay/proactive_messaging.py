"""Proactive Messaging Engine — 主动消息引擎

核心转变:
  以前: AI 等客户问 → AI 回复
  现在: AI 主动推进对话、追问信息、发送价值

触发条件:
  1. 客户回复后 AI 可以主动追问（不等人）
  2. 客户沉默超过 N 小时但状态活跃
  3. 客户在关键决策点（如报价后）

策略分类:
  - probe: 追问缺失信息（规格/数量/用途）
  - educate: 产品教育（材质/工艺/认证）
  - social_proof: 社会证明（案例/客户评价）
  - push: 推进成交（紧迫感/限量）

使用场景:
  在 orchestrator.decide() 中调用 should_be_proactive()
  如果 should=True，将生成的消息追加到回复末尾
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("proactive_messaging")

# ── 主动消息模板（按策略分类） ────────────────────────────

PROACTIVE_SCRIPTS = {
    "probe": {
        "specs": (
            "To give you the most accurate price, could you let me know "
            "the size and quantity you need?"
        ),
        "quantity": (
            "What quantity are you looking for? We offer volume discounts "
            "for bulk orders — the more you order, the better the unit price."
        ),
        "size": (
            "What size are you considering? We customize from 20cm letters "
            "up to 5m+ building signs."
        ),
        "usage": (
            "Where will this sign be installed? Indoor or outdoor? "
            "That affects the material recommendation."
        ),
        "color": (
            "Any specific color for the logo or text? We have 18 color options "
            "including RGB color-changing."
        ),
        "material": (
            "Do you have a preferred material? We offer stainless steel, "
            "acrylic, aluminum, and neon options."
        ),
    },
    "educate": {
        "quality": (
            "All our signs use export-grade LED beads with 50,000+ hours "
            "lifespan — that's about 5+ years of daily use."
        ),
        "material": (
            "We use SUS304 stainless steel for outdoor signs — "
            "it won't rust or fade for years even in harsh weather."
        ),
        "certification": (
            "Our products are CE, ROHS, and ISO certified. "
            "Quality is fully guaranteed with 2-year warranty."
        ),
        "warranty": (
            "We offer 2-year warranty on all our LED sign products. "
            "Full after-sales support including replacement parts."
        ),
        "shipping": (
            "We ship worldwide via sea or air. FOB Shenzhen or CIF to your port — "
            "we handle all logistics and customs documentation."
        ),
    },
    "social_proof": {
        "clients": (
            "We've supplied signage for clients in over 50 countries "
            "including US, UK, Germany, Australia, and UAE."
        ),
        "case": (
            "A client recently ordered our premium LED channel letters "
            "and was very satisfied with the quality and delivery time."
        ),
        "volume": (
            "We produce 500+ signs per month for global clients. "
            "Quality and on-time delivery are our top priorities."
        ),
        "satisfaction": (
            "98% of our clients say they would recommend us. "
            "We take quality very seriously — each sign goes through 3 quality checks."
        ),
    },
    "push": {
        "decision": (
            "I have a production slot available this week. "
            "If you confirm soon, I can lock in the current price."
        ),
        "limited": (
            "This price is valid until end of month. After that, "
            "new pricing takes effect due to material cost increases."
        ),
        "urgency": (
            "Our factory is currently at 80% capacity for this month. "
            "Early confirmation guarantees faster delivery."
        ),
    },
}


class ProactiveMessagingEngine:
    """主动消息引擎 — AI 不等客户，主动推进"""

    @staticmethod
    def should_be_proactive(customer, state, intent, history, message_text):
        """判断当前场景是否需要主动追问/推进

        基于销售阶段 + 客户意图 + 对话上下文综合判断。

        参数:
            customer: 客户信息 dict
            state: 当前销售状态
            intent: AI 意图分类
            history: 消息历史
            message_text: 客户最新消息

        返回:
            dict: {
                should: bool,
                strategy: str or None,
                slot: str or None,
                reason: str
            }
        """
        h = history or []

        # 1. 客户刚询价但信息不足 → 追问规格
        if intent == "pricing" and not _has_specs(message_text):
            return {
                "should": True,
                "strategy": "probe",
                "slot": "specs",
                "reason": "客户询价但缺少规格信息，主动追问规格数量",
            }

        # 2. 首次接触(NEW) → 问用途/场景
        if state == "NEW":
            return {
                "should": True,
                "strategy": "probe",
                "slot": "usage",
                "reason": "新客户首次接触，了解安装场景",
            }

        # 3. 客户问了产品但没问价格 → 主动给品质信息
        if intent == "product_inquiry":
            return {
                "should": True,
                "strategy": "educate",
                "slot": "quality",
                "reason": "客户关注产品，主动给品质认证信息",
            }

        # 4. QUALIFYING + 客户已说用途但没说数量 → 追问数量
        if state == "QUALIFYING" and intent == "general":
            return {
                "should": True,
                "strategy": "probe",
                "slot": "quantity",
                "reason": "了解需求阶段，追问数量以便报价",
            }

        # 5. 已报价多轮 → 加入社会证明增加信任
        if state == "PRICING" and len(h) >= 4:
            return {
                "should": True,
                "strategy": "social_proof",
                "slot": "clients",
                "reason": "已报价多轮，加入社会证明建立信任",
            }

        # 6. 谈判中 → 主动制造紧迫感
        if state == "NEGOTIATING":
            return {
                "should": True,
                "strategy": "push",
                "slot": "decision",
                "reason": "谈判阶段，主动创造紧迫感推进决策",
            }

        # 7. 默认不做主动追问
        return {
            "should": False,
            "strategy": None,
            "slot": None,
            "reason": "当前场景无需主动消息",
        }

    @staticmethod
    def generate_message(strategy, slot, customer=None, extra_context=None):
        """根据策略生成主动消息

        参数:
            strategy: 策略分类 (probe/educate/social_proof/push)
            slot: 具体话术槽位 (如 specs/quantity/quality)
            customer: 客户信息 dict（可选，用于个性化）
            extra_context: 额外上下文字典（可选）

        返回:
            str: 生成的消息，无可用时返回空字符串
        """
        scripts = PROACTIVE_SCRIPTS.get(strategy, {})
        msg = scripts.get(slot, "")

        if not msg:
            return ""

        # 个性化替换
        if customer:
            name = customer.get("name", "")
            if name and "{name}" in msg:
                msg = msg.replace("{name}", name)
            country = customer.get("country", "")
            if country and "{country}" in msg:
                msg = msg.replace("{country}", country)

        if extra_context:
            for key, val in extra_context.items():
                placeholder = "{" + key + "}"
                if placeholder in msg:
                    msg = msg.replace(placeholder, str(val))

        return msg

    @staticmethod
    def get_combined_reply(base_reply, customer, state, intent, history, message_text):
        """生成「基础回复 + 主动追问」合并回复

        这是推荐的一站式入口：
        1. 先生成基础回复
        2. 判断是否需要主动追问
        3. 如果需要，将追问追加到回复末尾

        参数:
            base_reply: 已有的基础回复内容
            customer: 客户信息 dict
            state: 当前销售状态
            intent: AI 意图分类
            history: 消息历史
            message_text: 客户最新消息

        返回:
            str: 追加主动消息后的完整回复
        """
        proactive = ProactiveMessagingEngine.should_be_proactive(
            customer, state, intent, history, message_text
        )

        if not proactive["should"]:
            return base_reply

        extra_msg = ProactiveMessagingEngine.generate_message(
            proactive["strategy"], proactive["slot"], customer
        )

        if extra_msg:
            combined = base_reply.rstrip()
            if not combined.endswith((".", "!", "?")):
                combined += "."
            return f"{combined}\n\n{extra_msg}"

        return base_reply

    @staticmethod
    def list_strategies():
        """获取所有可用策略（调试用）"""
        return {k: list(v.keys()) for k, v in PROACTIVE_SCRIPTS.items()}


def _has_specs(text):
    """检查客户消息中是否包含规格信息"""
    specs = [
        "cm", "mm", "m", "meter", "size", "dimension",
        "×", "x", "*", "wide", "long", "height", "large", "small",
        "米", "厘米", "毫米", "尺寸", "大小", "规格",
    ]
    return any(s in (text or "").lower() for s in specs)
