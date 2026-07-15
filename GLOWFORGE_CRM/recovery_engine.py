"""Recovery Engine — 流失追回系统

DELAYED 客户的 3 段式自动化跟进策略：
Step 1 (12h): 轻提醒不施压
Step 2 (12-24h): 价值重激活
Step 3 (48-72h): 机会稀缺

集成位置: ai_engine.py → _build_sales_strategy() → DELAYED 状态时注入
"""

# ==================== 3 段式跟进模板 ====================

RECOVERY_STEPS = {
    1: {
        "name": "轻提醒",
        "timing": "12h",
        "template": (
            "Just checking in — do you still want me to prepare "
            "the sign layout for your store?\n\n"
            "No pressure at all. Just wanted to leave the door open."
        ),
    },
    2: {
        "name": "价值重激活",
        "timing": "12-24h",
        "template": (
            "I was reviewing your case — your storefront actually "
            "has very strong visibility potential at night.\n\n"
            "If you still want, I can show you a quick before/after "
            "concept based on your photo.\n\n"
            "Just let me know and I'll put something together for you."
        ),
    },
    3: {
        "name": "机会稀缺",
        "timing": "48-72h",
        "template": (
            "We are currently scheduling new production slots "
            "for this week.\n\n"
            "If you want to proceed, I can still reserve one "
            "for your store design.\n\n"
            "Just confirm and I'll lock it in for you."
        ),
    },
}

RECOVERY_INSTRUCTION = """
===== Recovery Engine — 流失追回协议（当前客户状态: 犹豫延迟） =====
客户说"我再想想"或"回头找我"，进入 DELAYED 状态。

🔥 回复规则：
1. 理解认可 — "Take the time you need"
2. 留一个可执行的动作 — "If you want, I can prepare the layout first"
3. 铺垫下一次跟进 — "Let me check back in a few days"

🔥 绝对禁止：
  ❌ 逼单 — "you should decide now"
  ❌ 降价 — "I can give you a discount"
  ❌ 消失 — 必须铺垫下一次联系

🔥 参考话术（可自定义）：
"I completely understand — this is an important decision.
Take the time you need.

If you want, I can prepare the initial design layout
so you have something concrete to review.

I'll check back in a couple of days. No pressure at all."
============================================================
"""


class RecoveryEngine:
    """Recovery Engine — 3-step automated followup for DELAYED customers"""

    def __init__(self):
        self.steps = RECOVERY_STEPS

    def generate_step(self, step_number: int, context: dict = None) -> str:
        """Generate recovery message for given step number (1, 2, or 3)

        Args:
            step_number: 1=轻提醒, 2=价值重激活, 3=机会稀缺
            context: optional context for message customization
                - customer_name: customer name to insert
                - product: product type discussed
                - storefront_type: restaurant/bar/retail etc

        Returns:
            str: recovery message
        """
        step = self.steps.get(step_number)
        if not step:
            return ""

        msg = step["template"]
        if context:
            name = context.get("customer_name", "")
            if name:
                msg = msg.replace("your store", f"{name}'s store")
                msg = msg.replace("for you", f"for you, {name}")

        return msg

    def get_available_steps(self, history: list = None) -> list:
        """Determine which recovery steps have already been sent

        Args:
            history: message history [{role, content_en}, ...]

        Returns:
            list: step numbers that have NOT been sent yet
        """
        if not history:
            return [1, 2, 3]

        sent_steps = set()
        for h in history:
            text = (h.get("content_en", "") or h.get("text", "") or "").lower()
            if "just checking in" in text:
                sent_steps.add(1)
            if "visibility potential" in text or "before/after" in text:
                sent_steps.add(2)
            if "production slot" in text or "reserve one" in text:
                sent_steps.add(3)

        return [s for s in [1, 2, 3] if s not in sent_steps]


# ==================== 测试 ====================
if __name__ == "__main__":
    r = RecoveryEngine()
    for step in [1, 2, 3]:
        print(f"\n=== Step {step} ({r.steps[step]['name']}, {r.steps[step]['timing']}) ===")
        print(r.generate_step(step, {"customer_name": "John"}))

    print(f"\n=== Available steps (no history) ===")
    print(r.get_available_steps())

    print(f"\n=== Available steps (step 1 sent) ===")
    print(r.get_available_steps([{"role": "sent", "content_en": "Just checking in — do you still want..."}]))
