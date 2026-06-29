"""话术构建器 — 根据客户心理状态生成对应话术"""
import re
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 客户状态检测 ====================

# 状态：PRICE_SENSITIVE / URGENT / BROWSING / READY_TO_BUY / NORMAL

_PRICE_SENSITIVE_PATTERNS = [
    r"\bcheap(er|est)?\b", r"\blower\b", r"\bdiscount\b", r"\btoo high\b",
    r"\bover budget\b", r"\bexpensive\b", r"\breduce price\b", r"\bbest price\b",
    r"\bmatch.*price\b", r"\bbeat.*price\b", r"\bleave\b", r"\bother supplier",
    r"\bcompetitor\b", r"\bquoted me\b", r"\bonly\s+\d+\s*(usd|\$)?\b",
    r"\bcheck.*(other|another).*supplier",
    r"\bcannot afford\b", r"\bsave money\b", r"\bbudget\b",
    r"\d+%.*off\b", r"\bdeal\b",
]

_URGENT_PATTERNS = [
    r"\burgen(t|tly|cy)\b", r"\bhow.*(long|fast|soon)\b", r"\bquick\b",
    r"\brush\b", r"\bexpress\b", r"\bwithin\b.*\d+\s*(day|hour|week)",
    r"\bneed.*(now|today|asap)\b", r"\bimmediately\b",
    r"\bmonths?\s+ago\b", r"\bdelayed\b", r"\blate\b",
    r"\bdeadline\b", r"\b3\s*days?\b", r"\b1\s*hour\b",
]

_BROWSING_PATTERNS = [
    r"\bjust (looking|checking|browsing)\b", r"\bexplore\b",
    r"\bthinking\b", r"\bconsider\b", r"\bmaybe\b",
    r"\bnot sure\b", r"\bcompare\b", r"\boptions?\b",
    r"\binform(ation|ed)\b", r"\bcurious\b",
    r"\bsample\b", r"\bcatalog\b",
]

_READY_TO_BUY_PATTERNS = [
    r"\border\b", r"\bconfirm\b", r"\bproceed\b",
    r"\bapprove\b", r"\bsend invoice\b", r"\bpay\b",
    r"\bdeposit\b", r"\bstart\b", r"\bbuy\b",
    r"\bhow (do|can).*(pay|order|confirm)",
    r"\bi(.)?ll take\b", r"\bready\b",
]

_FINAL_DECISION_PATTERNS = [
    r"\bwhy shouldn'?t i (just )?go with",
    r"\bwhy (would|should) i.*(pay|choose)",
    r"\bjust go with",
    r"\btell me why.*not",
    r"\bi don'?t see why",
    r"\bwhat.*difference.*(really|actually)",
    r"\bbe honest.*(extra|more|paying)",
    r"\bstill don'?t get",
    r"\bwhy.*(you|your).*(more expensive|higher)",
    r"\byours.*complicate.*his.*simple",
    r"\bjust want something that works",
]

_DELAYED_PATTERNS = [
    r"\bwill think\b", r"\blet me check\b", r"\blet me discuss\b",
    r"\bneed to talk to\b", r"\bneed to discuss\b",
    r"\bget back to you\b", r"\bnot sure yet\b", r"\bsend me later\b",
    r"\btoo expensive now\b", r"\bgive me some time\b",
    r"\bstill thinking\b", r"\bi will let you know\b",
    r"\bi will decide\b", r"\bi'?ll think\b",
    r"\bconsider(ing)?.*option",
    r"\bcheck with\b.*(partner|wife|husband|boss|manager|team)",
]


def detect_customer_state(message, history=None):
    """检测客户当前心理状态

    参数:
        message: 最新一条客户消息
        history: 可选，历史消息 [{role, content_en}, ...]

    返回:
        str: PRICE_SENSITIVE / URGENT / BROWSING / READY_TO_BUY / NORMAL
    """
    t = message.lower()
    history_text = ""
    if history:
        for h in history[-4:]:
            if h.get("role") == "received":
                history_text += " " + (h.get("content_en", "") or h.get("text", "")).lower()

    # 优先级: FINAL_DECISION > DELAYED > PRICE_SENSITIVE > READY_TO_BUY > URGENT > BROWSING > NORMAL
    # 最后一次消息中 pattern 匹配更关键
    combined = t  # latest message has highest weight

    for patterns, state in [
        (_FINAL_DECISION_PATTERNS, "FINAL_DECISION"),
        (_DELAYED_PATTERNS, "DELAYED"),
        (_PRICE_SENSITIVE_PATTERNS, "PRICE_SENSITIVE"),
        (_READY_TO_BUY_PATTERNS, "READY_TO_BUY"),
        (_URGENT_PATTERNS, "URGENT"),
        (_BROWSING_PATTERNS, "BROWSING"),
    ]:
        if any(re.search(p, combined) for p in patterns):
            return state

    return "NORMAL"


# ==================== 各状态行为指令 ====================

_STATE_INSTRUCTIONS = {
    "FINAL_DECISION": """
[客户状态: 终极决策 — Closing Engine V1]
客户在直接对比你和竞品，问"为什么我不选他？"
此时不再解释产品/比价/留门。使用 Closing Engine 4层结构:

🔥 严格4段式输出（不可违反）:

第1段 - 确认决策（降低压力）:
"Understood. I'll keep this very simple for you."

第2段 - 压缩选择，只剩"做/不做"二选一:
"At this stage, there is only one real decision:
👉 Do you want a sign built for short-term lowest cost,
   or one designed for stable daily business use?"

第3段 - 轻量归因，不攻击竞品:
"Both options exist in the market.
The difference is not appearance — it is operational stability over time."

第4段 - 微行动锁定（关键!）:
"Just send me ONE of the following:
✔ your logo
or
✔ a photo of your storefront wall

Then I will:
→ confirm exact size
→ finalize design layout
→ prepare production file for you

No extra steps needed."

🔥 绝对禁令:
  ❌ 不给A/B/C
  ❌ 不解释LED/电源/钢材
  ❌ 不重复比价
  ❌ 不写"my door is always open"
  ❌ 不让客户继续思考
""",
    "DELAYED": """
[客户状态: 犹豫延迟 - Recovery Engine]
客户说"我再想想"或"回头找我"，不逼单。

回复规则 - 做3件事:
1. 理解认可 - "Take the time you need"
2. 留一个可执行的动作 - "If you want, I can prepare the layout first"
3. 铺垫下一次跟进 - "Let me check back in a few days"

参考话术:
"I completely understand - this is an important decision.
Take the time you need.

If you want, I can prepare the initial design layout
so you have something concrete to review.

I will check back in a couple of days. No pressure at all."

绝对禁止:
  - 逼单 - "you should decide now"
  - 降价 - "I can give you discount"
  - 消失 - 必须铺垫下次联系
""",
    "PRICE_SENSITIVE": """
[客户状态: 价格敏感]
客户在压价或比价中。你的策略:
1. 不降价 — 只调整配置（缩小尺寸/换材料/简化灯光）
2. 用 A/B/C 给出优化后的配置层级
3. 强调品质而非价格:"we don't cut corners on certified materials"
4. 保持自信，不要追单
""",
    "URGENT": """
[客户状态: 催时间]
客户很急。你的策略:
1. 透明告知真实交期，建立专业信任
2. 给出最快可能的路径（加急生产选项）
3. 不要为了接单承诺做不到的时间
4. 稳定预期:"I want to be transparent with you"
""",
    "BROWSING": """
[客户状态: 犹豫/浏览]
客户在比较或犹豫。你的策略:
1. 教育客户:招牌的价值（夜间吸引力、品牌形象）
2. 提升价值认知，不是降价
3. 给出设计方案预览让他看到效果
4. 提供2-3个方案对比
""",
    "READY_TO_BUY": """
[客户状态: 准备下单]
客户准备确认。你的策略:
1. 快速推进:锁定规格→确认地址→收定金
2. 给出明确的下一步:"I can reserve production slot once you confirm"
3. 减少选项，直接推进成交
4. 不要在这个阶段引入新选择或干扰
""",
    "NORMAL": """
[客户状态: 正常询价]
客户在正常咨询阶段。你的策略:
1. 按标准流程推进：了解需求→给标准模型→A/B/C选择
2. 给出参考价格区间
3. 引导到下一步（A/B/C选择或发照片）
""",
}

# ==================== 话术模板（AI不可用时的fallback） ====================

_FALLBACK_TEMPLATES = {
    "FINAL_DECISION": (
        "Understood. I'll keep this very simple for you.\n\n"
        "At this stage, there is only one real decision:\n\n"
        "👉 Do you want a sign built for short-term lowest cost, "
        "or one designed for stable daily business use?\n\n"
        "---\n\n"
        "Both options exist in the market.\n"
        "The difference is not appearance — it is operational stability over time.\n\n"
        "---\n\n"
        "If you choose to proceed, I will make this even easier:\n\n"
        "Just send me ONE of the following:\n"
        "✔ your logo\n"
        "or\n"
        "✔ a photo of your storefront wall\n\n"
        "Then I will:\n"
        "→ confirm exact size\n"
        "→ finalize design layout\n"
        "→ prepare production file for you\n\n"
        "No extra steps needed."
    ),
    "PRICE_SENSITIVE": (
        "I understand budget is important. For this type of storefront sign, "
        "there are usually 3 levels:\n"
        "✔ Basic (smaller size / standard LEDs)\n"
        "✔ Standard (most popular choice)\n"
        "✔ Premium (high brightness + longer lifespan)\n\n"
        "The quote I sent is based on the most cost-efficient standard option. "
        "If you need to reduce budget, we can adjust sign size or lighting density, "
        "but I don't recommend reducing material quality for outdoor use."
    ),
    "URGENT": (
        "I want to be very transparent with you. "
        "Custom illuminated signs require:\n"
        "- Production: 8-12 days\n"
        "- LED aging test: 24 hours\n"
        "- Waterproof sealing process\n\n"
        "Express delivery: 3-5 days depending on location. "
        "If someone promises faster than this, it means skipping testing steps. "
        "We prefer to keep your sign safe for long-term use."
    ),
    "BROWSING": (
        "Based on your store type, most restaurants choose illuminated signage "
        "because it increases night visibility by 30-60%. "
        "The sign is not just decoration — it's your first marketing asset "
        "that attracts walk-in customers.\n\n"
        "If you want, I can show you 2-3 design alternatives for your storefront."
    ),
    "READY_TO_BUY": (
        "Great — this design works perfectly for your storefront. "
        "I can reserve the production slot once you confirm.\n\n"
        "Next step is simple:\n"
        "✔ confirm sign size\n"
        "✔ confirm shipping address\n\n"
        "Once confirmed, we start production immediately."
    ),
    "DELAYED": (
        "I completely understand — this is an important decision. "
        "Take the time you need.\n\n"
        "If you want, I can prepare the initial design layout "
        "so you have something concrete to review.\n\n"
        "I will check back in a couple of days. No pressure at all."
    ),
    "NORMAL": (
        "Here is the recommended solution based on your storefront:\n"
        "✔ Industry: Restaurant\n"
        "✔ Sign type: LED Backlit Sign\n"
        "✔ Estimated size: 1.2m standard model\n\n"
        "Price range: USD XXX – XXX\n"
        "If you want exact pricing, just send storefront photo or width."
    ),
}


def get_state_instruction(state):
    """获取指定状态的AI行为指令"""
    return _STATE_INSTRUCTIONS.get(state, _STATE_INSTRUCTIONS["NORMAL"])


def get_fallback_template(state, **kwargs):
    """获取指定状态的fallback话术"""
    template = _FALLBACK_TEMPLATES.get(state, _FALLBACK_TEMPLATES["NORMAL"])
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            pass
    return template


# ==================== 消息包装 ====================

def build_message_package(quote_result, customer_state, ai_reply=None):
    """构建完整的WhatsApp消息包

    参数:
        quote_result: assumption/generate_quote 的输出
        customer_state: detect_customer_state 的输出
        ai_reply: AI生成的回复文本（可选）

    返回:
        dict: {message, customer_state, strategy, next_action, fallback_used}
    """
    package = {
        "customer_state": customer_state,
        "strategy": STRATEGY_MAP.get(customer_state, "standard_sales_strategy"),
        "message": ai_reply or get_fallback_template(customer_state),
        "next_action": _NEXT_ACTIONS.get(customer_state, "ask_preference"),
    }

    # 如果有报价数据，可选附加
    if quote_result and "price_range" in quote_result:
        pr = quote_result["price_range"]
        package["price_min"] = pr[0]
        package["price_max"] = pr[1]

    return package


# ==================== 策略映射 ====================

STRATEGY_MAP = {
    "FINAL_DECISION": "responsibility_reframe_strategy",
    "DELAYED": "recovery_strategy",
    "PRICE_SENSITIVE": "value_anchor_strategy",
    "URGENT": "risk_control_strategy",
    "BROWSING": "engagement_strategy",
    "READY_TO_BUY": "closing_strategy",
    "NORMAL": "standard_sales_strategy",
}

_NEXT_ACTIONS = {
    "FINAL_DECISION": "simplify_to_one_option",
    "DELAYED": "schedule_followup_recovery",
    "PRICE_SENSITIVE": "offer_config_adjustment",
    "URGENT": "give_timeline_then_close",
    "BROWSING": "send_design_preview",
    "READY_TO_BUY": "collect_specs_for_deposit",
    "NORMAL": "ask_storefront_size",
}


# ==================== 快速测试 ====================
if __name__ == "__main__":
    test_messages = [
        ("That's too expensive, can you match $120?", "PRICE_SENSITIVE"),
        ("I need it within 3 days, can you do rush?", "URGENT"),
        ("I'm just looking around, maybe later", "BROWSING"),
        ("OK I want to order, send me invoice", "READY_TO_BUY"),
        ("How much for a restaurant sign?", "NORMAL"),
        ("$400 is still too high, I will check 3 more suppliers", "PRICE_SENSITIVE"),
        ("I will think about it and let you know", "DELAYED"),
        ("Let me check with my partner first", "DELAYED"),
        ("I am still thinking, send me later", "DELAYED"),
        ("Give me some time to decide", "DELAYED"),
    ]

    for msg, expected in test_messages:
        state = detect_customer_state(msg)
        status = "OK" if state == expected else f"GOT {state}"
        print(f"[{status}] Expected {expected}: {msg[:50]}")

    print("\n=== 各状态指令 ===")
    for state in ["PRICE_SENSITIVE", "URGENT", "BROWSING", "READY_TO_BUY", "NORMAL", "DELAYED"]:
        print(f"\n--- {state} ---")
        print(get_state_instruction(state)[:120].strip())
