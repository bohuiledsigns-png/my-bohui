"""Re-entry Engine — 回流成交引擎

当 DELAYED 客户重新发消息时，自动恢复上下文，
输出 FINAL_DECISION-lite（不再重复解释），
直接继续上次的进度。

集成位置: ai_engine.py → _build_sales_strategy() → 检测到回流时注入
"""

import json
import re
from typing import Optional

# ==================== 上下文提取 ====================


def build_context_summary(history: list) -> dict:
    """从聊天历史中提取关键上下文

    Args:
        history: [{role, content_en}, ...]

    Returns:
        dict: {
            has_storefront_photo: bool,
            has_quote: bool,
            quote_amount: str,
            recommended_product: str,
            competitor_price: str,
            last_state: str,
            industry: str,
            mentioned_sizes: [str],
        }
    """
    summary = {
        "has_storefront_photo": False,
        "has_quote": False,
        "quote_amount": "",
        "recommended_product": "",
        "competitor_price": "",
        "last_state": "",
        "industry": "",
        "mentioned_sizes": [],
    }

    if not history:
        return summary

    full_text = " ".join(
        (h.get("content_en", "") or h.get("text", "") or "").lower()
        for h in history
    )

    # 照片/图片
    if any(w in full_text for w in ["photo", "screenshot", "image", "picture", "jpg", "png"]):
        summary["has_storefront_photo"] = True

    # 报价
    price_matches = re.findall(r"\$\d+", full_text)
    if price_matches:
        summary["has_quote"] = True
        amounts = [int(p.replace("$", "")) for p in price_matches if p.replace("$", "").isdigit()]
        if amounts:
            summary["quote_amount"] = f"${min(amounts)}-${max(amounts)}"

    # 产品推荐
    product_kw = {
        "front-glow": "front-glow LED sign",
        "backlit": "backlit LED sign",
        "halo": "halo backlit sign",
        "channel letter": "channel letter sign",
        "neon": "LED neon sign",
        "acrylic": "acrylic sign",
        "stainless": "stainless steel sign",
        "metal": "metal sign",
    }
    for kw, product in product_kw.items():
        if kw in full_text:
            summary["recommended_product"] = product
            break

    # 竞品价格
    comp_matches = re.findall(r"(?:other|competitor|cheaper|his).*?\$(\d+)", full_text)
    if comp_matches:
        summary["competitor_price"] = f"${min(int(x) for x in comp_matches)}"

    # 行业
    industry_kw = {
        "restaurant": "restaurant",
        "bar": "bar",
        "hotel": "hotel",
        "retail": "retail",
        "store": "retail",
        "shop": "retail",
        "office": "office",
    }
    for kw, industry in industry_kw.items():
        if kw in full_text:
            summary["industry"] = industry
            break

    # 尺寸
    size_matches = re.findall(r"(\d+\.?\d*)\s*(m|cm|ft|inch|inches|feet)", full_text)
    for num, unit in size_matches:
        summary["mentioned_sizes"].append(f"{num}{unit}")

    # 从最后几条消息推断状态
    recent_received = [h for h in history[-4:] if h.get("role") == "received"]
    if recent_received:
        last = recent_received[-1].get("content_en", "") or ""
        if any(p in last.lower() for p in ["think", "check", "later", "decide", "back to you"]):
            summary["last_state"] = "DELAYED"

    return summary


REENTRY_TEMPLATE = """\
Welcome back, {name}.

I have already prepared your previous storefront analysis.
To make this easy:

We already identified a suitable setup for your {industry}:
→ {product}

If you are ready, I can continue from where we left off
and finalize the layout in the next step.

Just confirm and I'll proceed right away.
"""

REENTRY_INSTRUCTION = """
===== Re-entry Engine — 回流成交协议（客户从延迟状态返回） =====
客户之前说"我再想想"，现在回来了。

🔥 核心原则：
1. 不提"你终于回来了"（不卑微）
2. 不重新解释产品/价格（客户已经知道）
3. 直接恢复上次进度 — "I've already prepared your analysis"
4. 输出 FINAL_DECISION-lite — 精简版收口

🔥 输出结构（3段式）：
第1段: 欢迎回 + 已准备好
"Welcome back. I've already prepared your previous storefront analysis."

第2段: 恢复进度—一句话说明上次的推荐
"We already identified a suitable setup for your restaurant."

第3段: 微行动推进
"If you're ready, I can continue and finalize the layout."

🔥 绝对禁止：
  ❌ 重新解释$115 vs $270的差异
  ❌ 重新列材料参数
  ❌ 再次给A/B/C
  ❌ 卑微语气 — "I'm glad you're back"
===============================================================
"""


class ReentryEngine:
    """Re-entry Engine — 恢复上下文，继续推进成交"""

    def __init__(self):
        self.template = REENTRY_TEMPLATE

    def build_context_summary(self, history: list) -> dict:
        """提取关键上下文"""
        return build_context_summary(history)

    def generate_reentry(self, context_summary: dict = None, history: list = None) -> str:
        """生成回流欢迎消息

        Args:
            context_summary: dict from build_context_summary()
            history: fallback if no context_summary provided

        Returns:
            str: re-entry message
        """
        if context_summary is None and history is not None:
            context_summary = build_context_summary(history)
        elif context_summary is None:
            context_summary = {}

        name = context_summary.get("customer_name", "there")
        industry = context_summary.get("industry", "storefront")
        product = context_summary.get("recommended_product", "LED sign")

        return self.template.format(
            name=name,
            industry=industry,
            product=product,
        )


# ==================== 测试 ====================
if __name__ == "__main__":
    test_history = [
        {"role": "received", "content_en": "How much for a restaurant sign?"},
        {"role": "sent", "content_en": "For a standard restaurant, $270-520 depending on size."},
        {"role": "received", "content_en": "Other quoted $115 with installation. Why should I pay more?"},
        {"role": "sent", "content_en": "I appreciate your honesty. The difference is operational stability over time."},
        {"role": "received", "content_en": "I will think about it and let you know."},
    ]

    ctx = build_context_summary(test_history)
    print("=== Context Summary ===")
    for k, v in ctx.items():
        print(f"  {k}: {v}")

    print("\n=== Re-entry Message ===")
    r = ReentryEngine()
    print(r.generate_reentry(ctx))
