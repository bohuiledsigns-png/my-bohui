"""Sales Executor Engine v2 — 状态→成交行为引擎

将 sales_state.py 的输出（state + price_tier + deal_probability）
转化为具体可执行的销售行为指令。

核心管道:
  state + price_tier + intent
    → sales_executor.execute()
      → reply_type + sales_instruction + quote_trigger
      → AI 生成最终回复

设计原则:
  - 不报价: NEW 阶段不给具体价格
  - 必给锚: 所有报价必须带价格锚
  - 必给3选1: 永远给 A/B/C 三档
  - 不教育: 不解释技术细节
  - 压风险: 异议阶段不降价，只讲风险差异
"""

# ==================== 价格锚配置 ====================

_PRICE_ANCHORS = {
    "LOW": {
        "range": "$120–200",
        "anchor": "$200",
        "abc": [
            {"label": "A — 入门款", "price": "$120-150", "desc": "基本功能，适合预算有限"},
            {"label": "B — 标准款", "price": "$150-180", "desc": "更高亮度，性价比之选"},
            {"label": "C — 升级款", "price": "$180-200", "desc": "全功能，效果最佳"},
        ],
        "risk_framing": "低价方案可能在户外6个月后开始褪色，更换成本更高。",
    },
    "MID": {
        "range": "$200–350",
        "anchor": "$280",
        "abc": [
            {"label": "A — 实用款", "price": "$200-250", "desc": "可靠耐用，适合大多数场景"},
            {"label": "B — 热销款", "price": "$250-300", "desc": "夜间高可见度，最受客户欢迎"},
            {"label": "C — 旗舰款", "price": "$300-350", "desc": "高端质感，使用寿命最长"},
        ],
        "risk_framing": "选择低价方案意味着 LED 可能在12个月后亮度衰减 30%，影响品牌形象。",
    },
    "HIGH": {
        "range": "$350+",
        "anchor": "$400",
        "abc": [
            {"label": "A — 标准高端", "price": "$350-400", "desc": "进口LED + 304不锈钢 + IP67防水"},
            {"label": "B — 奢华款", "price": "$400-500", "desc": "炫彩效果 + 双通道LED + 10年质保"},
            {"label": "C — 定制旗舰", "price": "$500+", "desc": "完全定制设计 + 安装服务 + 终身技术支持"},
        ],
        "risk_framing": "高端项目使用低端材料会导致 2-3 年后返工，总成本反超 3 倍。",
    },
    "UNKNOWN": {
        "range": "待确认",
        "anchor": "$250",
        "abc": [
            {"label": "A — 入门款", "price": "$120-200", "desc": "适合预算有限"},
            {"label": "B — 标准款", "price": "$200-300", "desc": "适合大多数需求"},
            {"label": "C — 高端款", "price": "$300+", "desc": "追求最佳品质和效果"},
        ],
        "risk_framing": "选择更可靠的品质意味着更低的长期维护成本。",
    },
}

# ==================== 各状态销售行为配置 ====================

_STATE_BEHAVIOR = {
    "NEW": {
        "reply_type": "ask",
        "whatsapp_action": "ask_info",
        "urgency_level": "low",
        "quote_trigger": False,
        "max_words": 80,
        "instruction_template": (
            "你是博汇销售。客户刚联系你。\n"
            "规则：\n"
            "1. 不要报价 — 绝不透露任何价格数字\n"
            "2. 要先了解需求 — 问什么类型、多大尺寸、装室内还是室外\n"
            "3. 给视觉效果预览 — '我们可以在1分钟内给你设计效果图'\n"
            "4. 简短2-3句，自然友好\n"
            "5. 引导客户发照片或尺寸"
        ),
    },
    "NEEDS_ANALYSIS": {
        "reply_type": "present_options",
        "whatsapp_action": "send_quote",
        "urgency_level": "medium",
        "quote_trigger": True,
        "max_words": 120,
        "instruction_template": (
            "你是博汇销售。客户在问价。\n"
            "规则：\n"
            "1. 先给价格区间：'most clients choose between {price_range}'\n"
            "2. 给A/B/C三档选项（用bullet point）：\n"
            "   {abc_options}\n"
            "3. 问一个关键信息（尺寸、数量、安装环境）\n"
            "4. 不要问太多问题 — 最多问1个\n"
            "5. 不要解释技术参数\n"
            "6. 结尾引导选择：'which one fits your needs best?'"
        ),
    },
    "BUDGET": {
        "reply_type": "anchor_price",
        "whatsapp_action": "send_quote",
        "urgency_level": "medium",
        "quote_trigger": True,
        "max_words": 100,
        "instruction_template": (
            "你是博汇销售。客户有预算但还没决定。\n"
            "规则：\n"
            "1. 锁定价格区间（用A/B/C三档）：\n"
            "   {abc_options}\n"
            "2. 必须包含价格锚：'Most {customer_type} choose between {price_range}'\n"
            "3. 不解释工艺/材质 — 客户不需要知道\n"
            "4. 不给折扣 — 用档位差异来匹配预算\n"
            "5. 结尾引导决定：'which tier works for your budget?'"
        ),
    },
    "OBJECTION": {
        "reply_type": "handle_objection",
        "whatsapp_action": "push_close",
        "urgency_level": "high",
        "quote_trigger": False,
        "max_words": 100,
        "instruction_template": (
            "你是博汇销售。客户在比价或嫌贵。\n"
            "规则：\n"
            "1. 不降价 — 绝不主动降价\n"
            "2. 不解释成本 — 客户不在乎你的成本\n"
            "3. 转风险框架：'低价方案在户外6个月后可能褪色，更换成本更高'\n"
            "4. 用社会证明：'大多数客户选择了{anchor_price}的档位，6个月后反馈很好'\n"
            "5. 强调差异化：品牌LED vs 无牌LED / 304不锈钢 vs 201不锈钢\n"
            "6. 简短2-3句，尊重客户但坚定\n"
            "7. 如果客户反复质疑，offer to send samples/certificates"
        ),
    },
    "FINAL": {
        "reply_type": "close",
        "whatsapp_action": "push_close",
        "urgency_level": "high",
        "quote_trigger": True,
        "max_words": 80,
        "instruction_template": (
            "你是博汇销售。客户要下单。\n"
            "规则：\n"
            "1. 不解释 — 客户已经决定了\n"
            "2. 给3个选项锁单：\n"
            "   {abc_options}\n"
            "3. 制造紧迫感：'we can start production this week if you confirm today'\n"
            "4. 明确下一步：'I'll send the invoice now — check your WhatsApp'\n"
            "5. 不要问 'are you sure?' — 直接推进\n"
            "6. 超简短1-2句"
        ),
    },
}

# ==================== 客户类型关键词 ====================

_CUSTOMER_TYPE_KEYWORDS = {
    "restaurant owner": ["restaurant", "cafe", "coffee shop", "bakery", "bar", "pub"],
    "retail store": ["store", "shop", "retail", "boutique", "showroom"],
    "hotel": ["hotel", "resort", "inn", "lodge", "motel"],
    "office": ["office", "corporate", "company", "business", "firm"],
    "distributor": ["distributor", "wholesale", "import", "OEM", "supply"],
    "contractor": ["contractor", "construction", "builder", "developer", "project"],
}


def _detect_customer_type(message):
    """检测客户类型，用于话术中的称呼"""
    t = message.lower()
    for ctype, keywords in _CUSTOMER_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return ctype
    return "client"


def _build_abc_text(abc_list):
    """将 A/B/C 选项列表格式化为文本"""
    lines = []
    for opt in abc_list:
        lines.append(f"  • {opt['label']}: {opt['price']} — {opt['desc']}")
    return "\n".join(lines)


class SalesExecutor:
    """销售执行器 — 状态→成交行为"""

    def execute(self, state_info, message="", country="", customer_name=""):
        """主入口

        Args:
            state_info: dict from sales_state.detect_sales_state()
            message: 客户原始消息
            country: 客户国家
            customer_name: 客户名字

        Returns:
            dict: {
                "reply_type": str,
                "sales_instruction": str,   # 注入 AI 提示词的指令
                "quote_trigger": bool,
                "whatsapp_action": str,
                "urgency_level": str,
                "price_anchor": str,
                "abc_options": list,
                "requires_risk_framing": bool,
            }
        """
        state = state_info.get("state", "NEW")
        price_tier = state_info.get("price_tier", "UNKNOWN")

        # 获取配置
        tier_config = _PRICE_ANCHORS.get(price_tier, _PRICE_ANCHORS["UNKNOWN"])
        behavior = _STATE_BEHAVIOR.get(state, _STATE_BEHAVIOR["NEW"])

        # 检测客户类型
        customer_type = _detect_customer_type(message) or "client"

        # 构建 A/B/C 选项文本
        abc_text = _build_abc_text(tier_config["abc"])

        # 填充 instruction 模板
        instruction = behavior["instruction_template"].format(
            price_range=tier_config["range"],
            anchor_price=tier_config["anchor"],
            abc_options=abc_text,
            customer_type=customer_type,
            customer_name=customer_name or customer_type,
        )

        # 是否需要风险压制（OBJECTION 或 LOW 梯级的 BUDGET）
        requires_risk = state in ("OBJECTION",) or (
            state == "BUDGET" and price_tier == "LOW"
        )

        return {
            "reply_type": behavior["reply_type"],
            "sales_instruction": instruction,
            "quote_trigger": behavior["quote_trigger"],
            "whatsapp_action": behavior["whatsapp_action"],
            "urgency_level": behavior["urgency_level"],
            "max_words": behavior["max_words"],
            "price_anchor": tier_config["range"],
            "anchor_price": tier_config["anchor"],
            "abc_options": tier_config["abc"],
            "abc_text": abc_text,
            "requires_risk_framing": requires_risk,
            "risk_framing": tier_config["risk_framing"],
            "customer_type": customer_type,
        }


# ==================== 快捷入口 ====================

def execute_sales_action(state_info, message="", country="", customer_name=""):
    """快捷调用 SalesExecutor"""
    executor = SalesExecutor()
    return executor.execute(state_info, message, country, customer_name)
