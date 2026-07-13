"""Sales Autopilot — 销售推进强制系统

不是「等客户决定」，是「系统主动推客户向下一个阶段」。

核心逻辑:
  1. 每次客户回复 → 检查是否需要强制推进到下一阶段
  2. 同一阶段停留超时 → 自动触发推进策略
  3. 推进策略包括: 追问规格/主动报价/逼单/PI推进

与 V1.1 StateSyncEngine 的关系:
  - StateSyncEngine 校验「是否合法」
  - SalesAutopilot 决定「应该往哪走」
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("sales_autopilot")

# 各状态最大停留天数（超时自动推进）
MAX_DWELL_DAYS = {
    "NEW": 3,
    "QUALIFYING": 7,
    "PRICING": 14,
    "NEGOTIATING": 14,
    "FOLLOWUP": 30,
    "COLD": 60,
}

# 强制推进策略
# 当客户在某个状态停留超时或触发条件时，自动推进
PROGRESSION_STRATEGIES = {
    "NEW": {
        "action": "probe_needs",
        "next_state": "QUALIFYING",
        "label": "需求探测",
    },
    "QUALIFYING": {
        "action": "offer_quote",
        "next_state": "PRICING",
        "label": "引导报价",
    },
    "PRICING": {
        "action": "push_decision",
        "next_state": "NEGOTIATING",
        "label": "决策推进",
    },
    "NEGOTIATING": {
        "action": "apply_closure_pressure",
        "next_state": "CLOSING",
        "label": "逼单",
    },
}


class SalesAutopilot:
    """销售推进强制系统 — 确保客户在销售漏斗中持续前进"""

    @staticmethod
    def evaluate(customer_id, current_state, intent, message_text, history):
        """评估是否需要强制推进状态

        参数:
            customer_id: 客户ID
            current_state: CRM当前状态
            intent: AI意图分类结果
            message_text: 客户最新消息
            history: 消息历史

        返回:
            dict: {
                force_progression: bool,
                proposed_state: str or None,
                strategy: str or None,
                reason: str
            }
        """
        t = (message_text or "").lower()

        # 1. 客户已经明确说 YES / 要下单 → 直接推进 CLOSING
        buying_signals = [
            "yes", "ok", "agree", "deal", "let's do it", "i want", "send me",
            "proceed", "i'll take", "place order", "下单", "可以", "好的",
            "做吧", "确认", "合同", "发票",
        ]
        if intent == "ready_to_order" or any(s in t for s in buying_signals):
            return {
                "force_progression": True,
                "proposed_state": "CLOSING",
                "strategy": "buying_signal",
                "reason": f"客户表达购买意图(intent={intent})，强制推进到CLOSING",
            }

        # 2. QUALIFYING + 客户已询价 → 推进 PRICING
        if current_state == "QUALIFYING" and intent in ("pricing", "product_inquiry"):
            return {
                "force_progression": True,
                "proposed_state": "PRICING",
                "strategy": "qualifying_to_pricing",
                "reason": "客户已询价，从QUALIFYING推进到PRICING",
            }

        # 3. PRICING + 客户在压价 → 推进 NEGOTIATING
        if current_state == "PRICING" and intent == "bargaining":
            return {
                "force_progression": True,
                "proposed_state": "NEGOTIATING",
                "strategy": "pricing_to_negotiating",
                "reason": "客户在压价，推进到NEGOTIATING",
            }

        # 4. NEGOTIATING + OK信号 → 推进 CLOSING
        ok_signals = [
            "ok", "yes", "deal", "agree", "send pi", "proceed",
            "可以", "好的", "做", "下单", "来",
        ]
        if current_state == "NEGOTIATING" and any(s in t for s in ok_signals):
            return {
                "force_progression": True,
                "proposed_state": "CLOSING",
                "strategy": "negotiating_to_closing",
                "reason": "客户在NEGOTIATING中表达认可，推进到CLOSING",
            }

        # 5. FOLLOWUP/COLD + 客户回复 → 拉回 актив目录
        if current_state in ("FOLLOWUP", "COLD"):
            return {
                "force_progression": True,
                "proposed_state": "QUALIFYING",
                "strategy": "reactivate",
                "reason": "沉默客户回复，重新激活到QUALIFYING",
            }

        # 6. 投诉 → 转 ESCALATED
        if intent == "complaint":
            return {
                "force_progression": True,
                "proposed_state": "ESCALATED",
                "strategy": "complaint_escalation",
                "reason": "客户投诉，转ESCALATED人工处理",
            }

        # 默认：不强制推进
        return {
            "force_progression": False,
            "proposed_state": None,
            "strategy": None,
            "reason": "当前无强制推进条件，保持现有状态",
        }

    @staticmethod
    def get_progression_strategy(state):
        """获取指定状态的推进策略"""
        return PROGRESSION_STRATEGIES.get(state)

    @staticmethod
    def get_max_dwell_days(state):
        """获取指定状态的最大停留天数"""
        return MAX_DWELL_DAYS.get(state, 30)

    @staticmethod
    def get_valid_progression_paths():
        """获取所有合法的强制推进路径（调试用）"""
        return {k: v for k, v in PROGRESSION_STRATEGIES.items()}
