"""V4 Conversion AI Brain — 决策大脑

回答3个问题:
1. 应该发消息吗？（should_send）
2. 发什么内容？（content_type）
3. 是否推成交？（push_close）

决策规则（按优先级）:
  inactive >= 72h           → SEND wake_up
  inactive >= 3h + A类       → SEND followup_light
  quote_viewed >= 2 + A/B类 → SEND push_close
  state=OBJECTION            → SEND risk_message
  push_count >= 3            → SEND final_close
  其他                      → WAIT
"""

import sys
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db


class ConversionBrain:
    """决策大脑"""

    def __init__(self):
        self._thresholds = {
            "inactivity_wake_hours": 72,
            "inactivity_followup_hours": 3,
            "quote_views_for_close": 2,
            "max_pushes_before_final": 3,
        }

    def decide(self, customer_id):
        """对客户做出完整决策

        Args:
            customer_id: 客户 ID

        Returns:
            dict: {
                should_send: bool,
                content_type: str (followup_light|push_close|risk_message|wake_up|final_close|none),
                push_close: bool,
                urgency: str (high|medium|low),
                reason: str,
                v4_conversion_score: int (0-100),
            }
        """
        conn = get_db()

        # 1. 获取客户基本信息
        cust = conn.execute(
            "SELECT id, country, status FROM customers WHERE id=?",
            (customer_id,)
        ).fetchone()
        if not cust:
            conn.close()
            return {"error": "customer not found"}

        # 2. 获取 v4 状态
        v4 = conn.execute(
            """SELECT priority_class, priority_score, priority_action,
                      last_activity_at, last_push_at, push_count,
                      quote_view_count, avg_reply_speed_hours
               FROM v4_customer_state WHERE customer_id=?""",
            (customer_id,)
        ).fetchone()

        # 3. 获取 v3 最新状态
        conv = conn.execute(
            """SELECT final_state, intent, conversion_score
               FROM v3_conversions
               WHERE customer_id=? AND final_result != 'open'
               ORDER BY id DESC LIMIT 1""",
            (customer_id,)
        ).fetchone()

        conn.close()

        if not v4:
            return {
                "should_send": False,
                "content_type": "none",
                "push_close": False,
                "urgency": "low",
                "reason": "no v4 state data (not yet scored)",
                "v4_conversion_score": 0,
            }

        # ====== 计算参数 ======
        priority_class = v4["priority_class"] or "C"
        priority_score = v4["priority_score"] or 0
        push_count = v4["push_count"] or 0
        quote_views = v4["quote_view_count"] or 0
        state = conv["final_state"] if conv else "NEW"
        inactivity_hours = self._get_inactivity_hours(v4["last_activity_at"])

        reasons = []
        should_send = False
        content_type = "none"
        push_close = False
        urgency = "low"

        # ====== 决策规则（按优先级） ======

        # Rule 1: inactive >= 72h → wake up
        if inactivity_hours >= self._thresholds["inactivity_wake_hours"]:
            should_send = True
            content_type = "wake_up"
            urgency = "medium"
            reasons.append(f"inactive {inactivity_hours}h >= 72h → wake_up")

        # Rule 2: inactive >= 3h + A class → followup_light
        elif inactivity_hours >= self._thresholds["inactivity_followup_hours"] and priority_class == "A":
            should_send = True
            content_type = "followup_light"
            urgency = "high"
            reasons.append(f"A-class inactive {inactivity_hours}h → followup_light")

        # Rule 3: quote viewed >= 2 + A/B class → push_close
        elif quote_views >= self._thresholds["quote_views_for_close"] and priority_class in ("A", "B"):
            should_send = True
            content_type = "push_close"
            push_close = True
            urgency = "high"
            reasons.append(f"quote viewed {quote_views}x, class {priority_class} → push_close")

        # Rule 4: OBJECTION → risk_message
        elif state == "OBJECTION":
            should_send = True
            content_type = "risk_message"
            urgency = "medium"
            reasons.append("state OBJECTION → risk_message")

        # Rule 5: push_count >= 3 → final_close
        elif push_count >= self._thresholds["max_pushes_before_final"]:
            should_send = True
            content_type = "final_close"
            push_close = True
            urgency = "high"
            reasons.append(f"push_count {push_count} >= 3 → final_close")

        else:
            reasons.append(f"no rule triggered (class={priority_class}, inactive={inactivity_hours}h, state={state})")

        # ====== 压制规则 ======
        # 如果已经推过很多次但仍然没有回复，降低频率
        if should_send and push_count >= 5:
            should_send = False
            reasons.append("suppressed: push_count >= 5")
            content_type = "none"

        return {
            "customer_id": customer_id,
            "should_send": should_send,
            "content_type": content_type,
            "push_close": push_close,
            "urgency": urgency,
            "reason": "; ".join(reasons),
            "v4_conversion_score": priority_score,
            "state": state,
            "priority_class": priority_class,
            "inactivity_hours": inactivity_hours,
            "push_count": push_count,
        }

    def get_next_step(self, customer_id):
        """获取客户下一步动作"""
        return self.decide(customer_id)

    def should_send(self, customer_id):
        """快速判断是否应该发消息"""
        decision = self.decide(customer_id)
        return decision.get("should_send", False)

    def get_content_type(self, customer_id):
        """获取应该发送的内容类型"""
        decision = self.decide(customer_id)
        return decision.get("content_type", "none") if decision.get("should_send") else "none"

    # ==================== 内部方法 ====================

    def _get_inactivity_hours(self, last_activity_at):
        """计算从最后活动到现在的间隔小时数"""
        if not last_activity_at:
            return 999  # 从未活动过
        try:
            if isinstance(last_activity_at, str):
                last = datetime.strptime(last_activity_at[:19].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            else:
                last = last_activity_at
            delta = datetime.now() - last
            return delta.total_seconds() / 3600
        except Exception:
            return 0


# ==================== 快捷入口 ====================

brain = ConversionBrain()


def decide_action(customer_id):
    return brain.decide(customer_id)
