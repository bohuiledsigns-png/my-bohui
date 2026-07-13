"""Closing Engine V1 — FINAL_DECISION 成交收口系统

在客户到达终极决策阶段时，不再解释产品/比价/留门，
而是用标准化4层结构完成收口，引导微行动锁定。

集成位置: script_builder.py → get_state_instruction("FINAL_DECISION")
           ai_engine.py → _build_sales_strategy() → FINAL_DECISION 时注入
"""

import re

# ==================== 关闭规则 ====================

CLOSING_RULES = {
    "no_pricing_explanation": True,   # 不再解释价格构成
    "no_material_details": True,      # 不再列LED/电源/钢材参数
    "no_open_endings": True,          # 不再"my door is always open"
    "max_options": 1,                 # 只剩"做/不做"一个选择
    "must_include_micro_action": True,  # 必须有一个极小下一步动作
    "no_a_b_c": True,                 # 不再给A/B/C
    "no_competitor_attack": True,     # 不攻击竞品
}

# ==================== 标准关闭模板 ====================

CLOSING_TEMPLATE = """\
Understood. I'll keep this very simple for you.

At this stage, there is only one real decision:

👉 Do you want a sign built for short-term lowest cost,
or one designed for stable daily business use?

---

Both options exist in the market.

The difference is not appearance — it is operational stability over time.

---

If you choose to proceed, I will make this even easier:

Just send me ONE of the following:
✔ your logo
or
✔ a photo of your storefront wall

Then I will:
→ confirm exact size
→ finalize design layout
→ prepare production file for you

No extra steps needed."""


def generate_closing(context: dict = None) -> str:
    """生成关闭消息

    Args:
        context: 可选上下文，包含:
            - competitor_price: 竞品价格，如 "$115"
            - our_price: 我方价格，如 "$270"
            - industry: 行业/客户类型
            - micro_action_options: 自定义微行动选项列表

    Returns:
        str: 关闭消息文本
    """
    msg = CLOSING_TEMPLATE

    if not context:
        return msg

    # 定制竞品价格
    comp = context.get("competitor_price", "")
    if comp:
        msg = msg.replace("short-term lowest cost", f"short-term lowest cost ({comp})")

    # 定制我方价格
    ours = context.get("our_price", "")
    if ours:
        msg = msg.replace(
            "stable daily business use",
            f"stable daily business use ({ours}+ standard)"
        )

    # 定制微行动选项
    micro_opts = context.get("micro_action_options", None)
    if micro_opts and len(micro_opts) >= 2:
        options_section = "Just send me ONE of the following:\n"
        for i, opt in enumerate(micro_opts[:3]):
            prefix = "✔ " if i == 0 else "or\n✔ "
            options_section += f"{prefix}{opt}\n"
        # 替换模板中的微行动部分
        old_micro = (
            "Just send me ONE of the following:\n✔ your logo\nor\n✔ a photo of your storefront wall"
        )
        msg = msg.replace(old_micro, options_section.strip())

    return msg


# ==================== 关闭指令（注入AI prompt用） ====================

CLOSING_INSTRUCTION = """
===== Closing Engine — 成交收口协议（当前客户状态: 终极决策） =====
你已进入终极收口阶段。禁止一切产品解释、价格对比、开放结尾。

🔥 输出结构 — 严格4段式（强制遵守）：
第1段: 确认决策，降低压力。一句话：
  "Understood. I'll keep this very simple for you."

第2段: 压缩选择 — 只剩"做/不做"二选一。不是A/B/C，是：
  "At this stage, there is only one real decision:
   👉 Do you want a sign built for short-term lowest cost,
      or one designed for stable daily business use?"

第3段: 轻量风险归因 — 不攻击竞品，只陈述事实差别：
  "Both options exist in the market.
   The difference is not appearance — it is operational stability over time."

第4段: 微行动锁定（关键） — 引导一个极小具体动作，不是问"买不买"：
  "Just send me ONE of the following: ✔ your logo or ✔ a photo of your storefront wall
   Then I will: confirm exact size → finalize design layout → prepare production file"

🔥 绝对禁令（违反会损失客户）：
  ❌ 不给A/B/C（只剩做/不做）
  ❌ 不解释LED/电源/钢材（不再讲产品）
  ❌ 不重复比价（价格已经比过了）
  ❌ 不写"my door is always open"（不留门）
  ❌ 不让客户继续思考（直接给下一步动作）

🔥 suggested_reply_en 纯英文，严格4段式，包含微行动锁定。
============================================================
"""

# ==================== 验证 ====================

# 违规关键词（如果在关闭消息中出现，说明不合格）
_FORBIDDEN_PATTERNS = [
    r"my door", r"always open", r"feel free", r"if you change your mind",
    r"let me know if you", r"no rush", r"take your time",
    r"waterproof rating", r"LED.*brand", r"power supply",
    r"stainless steel", r"acrylic.*thickness",
    r"option a", r"option b", r"option c",
    r"A\)", r"B\)", r"C\)",
]

_REQUIRED_PATTERNS = [
    r"keep this very simple",
    r"only one real decision",
    r"short-term.*lowest cost|stable.*business use",
    r"Just send me|send me ONE|confirm.*logo|photo.*storefront",
]


def validate_closing(message: str) -> dict:
    """验证关闭消息是否符合 Closing Engine 规则

    Returns:
        dict: {pass: bool, errors: [str], warnings: [str]}
    """
    t = message.lower()
    errors = []
    warnings = []

    # 检查违规
    for pat in _FORBIDDEN_PATTERNS:
        if re.search(pat, t):
            errors.append(f"包含违规表达: {pat}")

    # 检查必需元素
    for pat in _REQUIRED_PATTERNS:
        if not re.search(pat, t):
            warnings.append(f"缺少必需元素: {pat}")

    # 结构检查
    sentences = len([s for s in re.split(r'[.!?\n]', t) if s.strip()])
    if sentences > 20:
        warnings.append(f"可能过长 ({sentences} 句)，建议控制在12句以内")

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ==================== 测试 ====================
if __name__ == "__main__":
    print("=== Closing Engine V1 ===\n")
    print(generate_closing({"competitor_price": "$115", "our_price": "$270"}))
    print(f"\n=== 验证结果 ===")
    result = validate_closing(generate_closing())
    print(f"通过: {result['pass']}")
    if result["errors"]:
        print(f"错误: {result['errors']}")
    if result["warnings"]:
        print(f"警告: {result['warnings']}")
