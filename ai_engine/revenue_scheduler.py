"""V4 Revenue Scheduler — 收单调度器

每日调度时间表:
  09:00 → 推A类客户 (高意向逼单)
  12:00 → 跟进B类客户 (温和跟进)
  18:00 → 唤醒冷客户 (冷养触达)
  22:00 → 收尾逼单 (最终成交push)

运行机制:
  - threading.Thread + Event().wait(60) 每分钟检查
  - 匹配时段 (30分钟窗口) 后执行
  - 每个tick: 重新评分 → 决策 → 发送 → 记录日志
"""

import sys
import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db


# ==================== 调度时间表 ====================

_SCHEDULE = [
    {"time": "09:00", "label": "Morning Push",       "action": "push_a_class",      "target_class": "A", "content_type": "push_close"},
    {"time": "12:00", "label": "Noon Follow-up",     "action": "follow_b_class",    "target_class": "B", "content_type": "followup_light"},
    {"time": "18:00", "label": "Evening Wake-up",    "action": "wake_cold",         "target_class": "C", "content_type": "wake_up"},
    {"time": "22:00", "label": "Night Final Close",  "action": "final_close_push",  "target_class": "A", "content_type": "push_close"},
]

# 30分钟检查窗口
_TIME_WINDOW_MINUTES = 30


class RevenueScheduler:
    """收单调度器"""

    def __init__(self):
        self._last_run_slots = {}  # slot_name → date string
        self._enabled = True

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value

    def run_scheduled_tick(self):
        """每分钟调用一次的调度 tick

        检查是否到达指定时段，如果是则执行对应动作。

        Returns:
            dict: {slot, action, checked, sent, skipped, errors}
        """
        if not self._enabled:
            return {"slot": None, "action": "disabled", "checked": 0, "sent": 0, "skipped": 0, "errors": 0}

        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        # 检查哪个时段匹配
        matched_slot = None
        for slot in _SCHEDULE:
            if self._is_time_match(current_time, slot["time"]):
                matched_slot = slot
                break

        if not matched_slot:
            return {"slot": None, "action": "no_match", "checked": 0, "sent": 0, "skipped": 0, "errors": 0}

        slot_key = f"{matched_slot['action']}_{today}"

        # 防止一天内重复执行
        if self._last_run_slots.get(slot_key):
            return {"slot": matched_slot["label"], "action": "already_run", "checked": 0, "sent": 0, "skipped": 0, "errors": 0}

        self._last_run_slots[slot_key] = True

        # 执行调度动作
        return self._execute_slot(matched_slot)

    def _execute_slot(self, slot):
        """执行一个时段的调度动作

        Args:
            slot: _SCHEDULE 中的一个条目

        Returns:
            dict: 执行结果
        """
        from ai_engine.deal_prioritizer import DealPrioritizer
        from ai_engine.conversion_ai_brain import ConversionBrain
        from ai_engine.autonomous_sender import AutonomousSender

        prioritizer = DealPrioritizer()
        brain = ConversionBrain()
        sender = AutonomousSender()

        # 1. 重新评分所有客户
        try:
            prioritizer.batch_reprioritize(limit=200)
        except Exception as e:
            return {"slot": slot["label"], "action": slot["action"], "error": f"reprioritize failed: {e}"}

        # 2. 获取目标分类的客户
        target_class = slot["target_class"]
        customers = prioritizer.get_by_class(target_class)

        results = {"slot": slot["label"], "action": slot["action"],
                   "checked": len(customers), "sent": 0, "skipped": 0, "errors": 0}

        for cust in customers:
            customer_id = cust["customer_id"]

            # 3. 决策
            decision = brain.decide(customer_id)
            if not decision.get("should_send"):
                results["skipped"] += 1
                self._log_activity(slot["action"], customer_id, "skipped",
                                   f"brain decided not to send: {decision.get('reason', '')[:100]}")
                continue

            # 4. 发送
            try:
                send_result = sender.send_by_decision(customer_id, decision)
                if send_result.get("sent"):
                    results["sent"] += 1
                    self._log_activity(slot["action"], customer_id, "completed",
                                       f"type={decision.get('content_type')}")
                else:
                    results["skipped"] += 1
                    self._log_activity(slot["action"], customer_id, "skipped",
                                       send_result.get("reason", "send returned false"))
            except Exception as e:
                results["errors"] += 1
                self._log_activity(slot["action"], customer_id, "error", str(e)[:200])

        return results

    def manual_run(self, slot_name=None):
        """手动触发调度

        Args:
            slot_name: 可选，指定时段名称 (09:00/12:00/18:00/22:00)

        Returns:
            dict: 执行结果
        """
        if slot_name:
            for slot in _SCHEDULE:
                if slot["time"] == slot_name:
                    return self._execute_slot(slot)
            return {"error": f"slot '{slot_name}' not found"}
        else:
            # 运行最近匹配的时段
            now = datetime.now().strftime("%H:%M")
            for slot in _SCHEDULE:
                if self._is_time_match(now, slot["time"], window_minutes=120):
                    return self._execute_slot(slot)
            # 如果都不匹配，运行默认的 (09:00)
            return self._execute_slot(_SCHEDULE[0])

    def get_status(self):
        """获取调度器状态"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 今天已运行的时段
        conn = get_db()
        today_log = conn.execute(
            """SELECT schedule_slot, action, COUNT(*) as runs,
                      SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                      SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors
               FROM v4_scheduler_log
               WHERE date(created_at) = ?
               GROUP BY schedule_slot, action
               ORDER BY schedule_slot""",
            (today,)
        ).fetchall()
        conn.close()

        # 找出当前应该运行的时段
        current_time = now.strftime("%H:%M")
        active_slot = None
        for slot in _SCHEDULE:
            if self._is_time_match(current_time, slot["time"]):
                active_slot = slot
                break

        return {
            "enabled": self._enabled,
            "current_time": current_time,
            "active_slot": active_slot,
            "today_log": [dict(r) for r in today_log],
            "schedule": _SCHEDULE,
        }

    def get_today_log(self):
        """获取今日调度日志"""
        conn = get_db()
        rows = conn.execute(
            """SELECT sl.*, c.name as customer_name
               FROM v4_scheduler_log sl
               LEFT JOIN customers c ON sl.customer_id = c.id
               WHERE date(sl.created_at) = date('now')
               ORDER BY sl.created_at DESC
               LIMIT 100"""
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ==================== 内部方法 ====================

    def _is_time_match(self, current_time, slot_time, window_minutes=None):
        """检查当前时间是否在时段窗口内"""
        if window_minutes is None:
            window_minutes = _TIME_WINDOW_MINUTES

        try:
            h, m = map(int, current_time.split(":"))
            sh, sm = map(int, slot_time.split(":"))
            current_minutes = h * 60 + m
            slot_minutes = sh * 60 + sm
            return abs(current_minutes - slot_minutes) <= window_minutes
        except Exception:
            return False

    def _log_activity(self, action, customer_id, status, detail=""):
        """记录调度活动到 v4_scheduler_log"""
        conn = get_db()
        # 确定时段标签
        slot_label = action
        for s in _SCHEDULE:
            if s["action"] == action:
                slot_label = s["time"]
                break

        conn.execute(
            """INSERT INTO v4_scheduler_log
               (schedule_slot, action, customer_id, status, detail)
               VALUES (?,?,?,?,?)""",
            (slot_label, action, customer_id, status, detail[:300])
        )
        conn.commit()
        conn.close()


# ==================== 快捷入口 ====================

scheduler = RevenueScheduler()


def run_scheduler_tick():
    return scheduler.run_scheduled_tick()


def start_v4_scheduler_background():
    """启动 v4 调度器后台线程（在 app.py 中调用）"""
    import threading

    def _v4_scheduler_loop():
        sched = RevenueScheduler()
        while True:
            try:
                result = sched.run_scheduled_tick()
                if result.get("sent", 0) > 0 or result.get("errors", 0) > 0:
                    print(f"[v4 Scheduler] {result['slot']}: sent={result['sent']} skipped={result['skipped']} errors={result['errors']}")
            except Exception as e:
                print(f"[v4 Scheduler] Error: {e}")
            threading.Event().wait(60)  # 每分钟检查一次

    threading.Thread(target=_v4_scheduler_loop, daemon=True).start()
    return True
