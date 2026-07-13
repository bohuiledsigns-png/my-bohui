"""Pricing Lock Engine — 防砍价引擎

当回流客户再次提及竞品低价时，系统不重新解释工艺细节，
而是执行"框架重置"（frame reset）：
- 不争论
- 不压人
- 只重置框架：$115 是入门级，$270+ 是稳定运营级

集成位置: ai_engine.py → _build_sales_strategy() → 检测到砍价时注入
"""

import re
from typing import Optional

# ==================== 砍价信号检测 ====================

_RENEGOTIATION_PATTERNS = [
    # 直接提旧价格
    r"\$?\d{2,3}.*(?:still|better|too much|cheaper)",
    r"(?:still|but).*\$?\d{2,3}",
    # 对比竞品
    r"other.*(?:price|quote|offer|supplier)",
    r"(?:competitor|other guy).*\$",
    r"his.*price",
    # 要求降价
    r"(?:still|too).*(?:expensive|high|much)",
    r"can you.*(?:lower|reduce|match|beat)",
    r"(?:any|better).*(?:price|deal|discount)",
    r"give me.*(?:better|lower|special)",
    # 质疑价值
    r"why.*(?:still|so).*(?:much|expensive)",
    r"worth.*that.*much",
]

_PRICE_MENTION_PATTERN = re.compile(r"\$(\d+)")


# ==================== 框架重置模板 ====================

FRAME_RESET_TEMPLATE = """\
I understand.

Just to be transparent — $115 options are typically entry-level signage
designed for short-term or basic visibility use.

For {industry} storefronts that run daily lighting,
most of our clients stay in the ${our_price}+ range
for stability and maintenance reasons.

We can absolutely proceed with either —
it depends on your usage goal."""
# Note: ends open — lets customer re-choose without pressure

PRICING_LOCK_INSTRUCTION = """
===== Pricing Lock Engine — 防砍价协议（客户再次提低价时触发） =====
客户之前已经比过价，现在回来再次提 $115/$120 竞品低价。

🔥 核心原则：
1. 不争论 — 不解释材料/电源/LED差异
2. 不攻击 — 不贬低竞品质量
3. 只重置框架 — 把"哪个便宜"转成"哪个适合你的使用场景"

🔥 标准话术结构：
第1段: 理解认可 — "I understand. Just to be transparent..."
第2段: 框架重置 — "$115 options are entry-level for short-term use.
         For daily restaurant lighting, most clients stay in $270+ range."
第3段: 开放选择 — "We can proceed with either — it depends on your usage goal."

🔥 绝对禁止：
  ❌ 重新解释LED/电源/不锈钢等级
  ❌ 说"你上次不是已经知道了吗"
  ❌ 降价
  ❌ 攻击竞品
============================================================
"""


class PricingLockEngine:
    """Pricing Lock Engine — 检测+防御砍价"""

    def __init__(self):
        self.patterns = _RENEGOTIATION_PATTERNS

    def detect_renegotiation(self, message: str, history: list = None) -> bool:
        """检测客户是否在试图重新砍价

        Args:
            message: customer's latest message
            history: optional chat history

        Returns:
            bool: True if customer is renegotiating
        """
        t = message.lower()

        # 必须包含价格数字才触发
        has_price = bool(_PRICE_MENTION_PATTERN.search(t))
        if not has_price:
            return False

        # 检查模式匹配
        for pattern in self.patterns:
            if re.search(pattern, t):
                return True

        # 如果有历史记录，检查是否曾经比过价
        if history:
            full_text = " ".join(
                (h.get("content_en", "") or h.get("text", "") or "").lower()
                for h in history
            )
            had_price_comparison = any(
                p in full_text for p in [
                    "other quoted", "competitor", "cheaper",
                    "$115", "$120", "$95", "$90",
                    "other supplier",
                ]
            )
            if had_price_comparison and has_price:
                return True

        return False

    def generate_frame_reset(self, context: dict = None) -> str:
        """生成框架重置消息

        Args:
            context: {
                industry: "restaurant" / "bar" / "retail"
                our_price: 270,
                competitor_price: 115,
                customer_name: str,
            }

        Returns:
            str: frame reset message
        """
        ctx = context or {}
        industry = ctx.get("industry", "storefront")
        our_price = ctx.get("our_price", 270)
        competitor_price = ctx.get("competitor_price", 115)

        msg = FRAME_RESET_TEMPLATE.format(
            industry=industry,
            our_price=our_price,
        )

        # 替换具体竞品价格
        msg = msg.replace("$115", f"${competitor_price}")
        msg = msg.replace("$270", f"${our_price}")

        return msg

    def should_lock_pricing(self, customer_state: str, message: str, history: list = None) -> bool:
        """综合判断是否需要启用防砍价

        Args:
            customer_state: current detected state
            message: latest customer message
            history: chat history

        Returns:
            bool: True if pricing lock should activate
        """
        # FINAL_DECISION + 再次提价 = 防砍价
        if customer_state in ("FINAL_DECISION", "DELAYED"):
            return self.detect_renegotiation(message, history)
        return False


# ==================== 测试 ====================
if __name__ == "__main__":
    engine = PricingLockEngine()

    test_cases = [
        ("$115 is still better than $270", True),
        ("can you match $120?", True),
        ("how much for a standard sign?", False),
        ("what's your best price for 10 units?", False),
        ("other supplier still has $95 option", True),
        ("I will think about it", False),
    ]

    print("=== Renegotiation Detection ===")
    for msg, expected in test_cases:
        result = engine.detect_renegotiation(msg)
        status = "OK" if result == expected else f"GOT {result}"
        print(f"[{status}] Expected {expected}: {msg[:50]}")

    print("\n=== Frame Reset ===")
    print(engine.generate_frame_reset({
        "industry": "restaurant",
        "our_price": 270,
        "competitor_price": 115,
    }))
