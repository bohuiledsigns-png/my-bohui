"""Stabilization Layer — V1.1 稳定层

把「散装 AI 能力」收敛为「统一受控销售系统」。

四个核心模块:
  1. StateSyncEngine  — CRM 为唯一状态源，AI 只能提议
  2. ConversationLock — 活跃对话期间禁止跟进/干扰
  3. ConfidenceGate   — 置信度门控，防止 AI 过度决策
  4. FollowUpGuard    — 跟进冲突控制器，冷却规则

架构原则:
  CRM = Source of Truth
  AI  = 只读 + 提议状态变更
  禁止状态跳跃
  活跃对话冻结跟进
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logger = logging.getLogger("stabilization")


# ═══════════════════════════════════════════════════════════
# 1. StateSyncEngine — 状态一致性引擎
# ═══════════════════════════════════════════════════════════

# 合法流转白名单（禁止跳跃）
VALID_TRANSITIONS = {
    "NEW":           ["QUALIFYING"],
    "QUALIFYING":    ["PRICING", "FOLLOWUP", "COLD"],
    "PRICING":       ["NEGOTIATING", "CLOSING", "FOLLOWUP", "COLD"],
    "NEGOTIATING":   ["CLOSING", "PRICING", "FOLLOWUP", "ESCALATED", "COLD"],
    "CLOSING":       ["CLOSED_WON", "CLOSED_LOST", "NEGOTIATING"],
    "FOLLOWUP":      ["QUALIFYING", "PRICING", "COLD"],
    "COLD":          ["QUALIFYING"],
    "ESCALATED":     ["CLOSING", "CLOSED_WON"],
    "CLOSED_WON":    ["FOLLOWUP"],
    "CLOSED_LOST":   ["COLD"],
}


class StateSyncEngine:
    """状态一致性引擎

    CRM 是唯一事实源。AI 只能提议状态变更，由本引擎校验后决定是否执行。
    """

    @staticmethod
    def is_valid_transition(current_state, proposed_state):
        """检查状态变更是否合法"""
        if current_state == proposed_state:
            return True
        allowed = VALID_TRANSITIONS.get(current_state, [])
        return proposed_state in allowed

    @staticmethod
    def propose(crm_state, ai_proposal):
        """AI 提议状态变更 → 引擎校验 → 返回最终状态

        参数:
            crm_state: CRM 当前状态
            ai_proposal: AI 提议的新状态或 None

        返回:
            dict: {state, changed, reason}
        """
        if not ai_proposal or ai_proposal == crm_state:
            return {"state": crm_state, "changed": False, "reason": "状态无变化"}

        if StateSyncEngine.is_valid_transition(crm_state, ai_proposal):
            logger.info(f"[StateSync] {crm_state} → {ai_proposal} (valid)")
            return {"state": ai_proposal, "changed": True, "reason": f"合法流转: {crm_state}→{ai_proposal}"}

        logger.warning(f"[StateSync] 拒绝跳跃: {crm_state} → {ai_proposal}")
        return {
            "state": crm_state,
            "changed": False,
            "reason": f"禁止状态跳跃: {crm_state} 不能直接到 {ai_proposal}",
        }

    @staticmethod
    def get_next_states(current_state):
        """获取当前状态可以流转到的所有合法状态"""
        return VALID_TRANSITIONS.get(current_state, [])


# ═══════════════════════════════════════════════════════════
# 2. ConversationLock — 会话锁
# ═══════════════════════════════════════════════════════════

class ConversationLock:
    """会话锁 — 防止跟进/调度打扰活跃对话"""

    # 每个客户的上次消息时间（内存缓存，进程级）
    _last_message_at = {}
    _ai_processing = set()

    # 冷却时间配置（秒）
    LOCK_MINUTES = 30          # 30分钟内有过消息 → 锁定
    FOLLOWUP_COOLDOWN_HOURS = 24  # 24小时内有过消息 → 跟进冷却

    @classmethod
    def record_message(cls, customer_id, direction="received"):
        """记录客户消息时间"""
        cls._last_message_at[customer_id] = {
            "time": time.time(),
            "direction": direction,
        }
        # 收到客户消息时解锁 AI 处理状态
        if direction == "received":
            cls._ai_processing.discard(customer_id)

    @classmethod
    def mark_ai_processing(cls, customer_id):
        """标记 AI 正在处理中"""
        cls._ai_processing.add(customer_id)

    @classmethod
    def mark_ai_done(cls, customer_id):
        """标记 AI 处理完成"""
        cls._ai_processing.discard(customer_id)

    @classmethod
    def is_locked(cls, customer_id):
        """检查客户会话是否锁定

        满足任一条件即锁定:
          - 最近 LOCK_MINUTES 内有消息
          - AI 正在处理中
        """
        record = cls._last_message_at.get(customer_id)
        if record:
            elapsed = time.time() - record["time"]
            if elapsed < cls.LOCK_MINUTES * 60:
                return True
        if customer_id in cls._ai_processing:
            return True
        return False

    @classmethod
    def can_followup(cls, customer_id):
        """检查是否允许跟进

        跟进冷却规则:
          - 客户最近 24h 内有消息 → 不允许
          - 会话锁定中 → 不允许
        """
        if cls.is_locked(customer_id):
            return False
        record = cls._last_message_at.get(customer_id)
        if record:
            elapsed = time.time() - record["time"]
            if elapsed < cls.FOLLOWUP_COOLDOWN_HOURS * 3600:
                return False
        return True

    @classmethod
    def status(cls, customer_id):
        """获取当前会话锁状态（调试用）"""
        record = cls._last_message_at.get(customer_id)
        now = time.time()
        return {
            "locked": cls.is_locked(customer_id),
            "can_followup": cls.can_followup(customer_id),
            "last_message_seconds_ago": int(now - record["time"]) if record else None,
            "ai_processing": customer_id in cls._ai_processing,
        }


# ═══════════════════════════════════════════════════════════
# 3. ConfidenceGate — 置信度门控
# ═══════════════════════════════════════════════════════════

# 置信度阈值
AUTO_EXECUTE_THRESHOLD = 0.85    # >= 0.85: 自动执行
LOGGED_EXECUTE_THRESHOLD = 0.60  # >= 0.60: 允许执行 + 记录
# < 0.60: 只建议，不执行


class ConfidenceGate:
    """置信度门控 — 防止 AI 过度自信推进成交"""

    # 高风险动作（需要更高置信度）
    HIGH_RISK_ACTIONS = {"escalate", "close", "send_pi", "discount"}

    @staticmethod
    def evaluate(confidence, action, state=None):
        """评估是否允许执行

        参数:
            confidence: AI 置信度 0.0-1.0
            action: 提议的动作
            state: 当前销售状态（可选）

        返回:
            dict: {
                allowed: bool,
                level: str (auto / logged / advisory),
                reason: str
            }
        """
        # 高风险动作提阈值
        effective_threshold = AUTO_EXECUTE_THRESHOLD
        if action in ConfidenceGate.HIGH_RISK_ACTIONS:
            effective_threshold += 0.10
            # CLOSING 状态下的高风险动作需更高阈值
            if state == "CLOSING":
                effective_threshold = 0.95

        if confidence >= effective_threshold:
            return {
                "allowed": True,
                "level": "auto",
                "reason": f"置信度 {confidence:.2f} >= {effective_threshold:.2f}，自动执行",
            }

        if confidence >= LOGGED_EXECUTE_THRESHOLD:
            return {
                "allowed": True,
                "level": "logged",
                "reason": f"置信度 {confidence:.2f} >= {LOGGED_EXECUTE_THRESHOLD:.2f}，允许执行（需记录）",
            }

        return {
            "allowed": False,
            "level": "advisory",
            "reason": f"置信度 {confidence:.2f} 不足 {LOGGED_EXECUTE_THRESHOLD:.2f}，仅建议不执行",
        }

    @staticmethod
    def safe_output(state, confidence, action, reply=""):
        """生成标准化的受控输出

        返回:
            dict: 可直接用于 orchestrator 返回
        """
        gate = ConfidenceGate.evaluate(confidence, action, state)
        return {
            "state": state,
            "confidence": round(confidence, 2),
            "action": action,
            "reply": reply,
            "safe_to_execute": gate["allowed"],
            "execution_level": gate["level"],
            "gate_reason": gate["reason"],
        }


# ═══════════════════════════════════════════════════════════
# 4. FollowUpGuard — 跟进冲突控制器
# ═══════════════════════════════════════════════════════════

# 禁止跟进的状态
FOLLOWUP_BLOCKED_STATES = {
    "NEW", "QUALIFYING", "PRICING",
    "NEGOTIATING", "CLOSING", "ESCALATED",
}

# 允许跟进的状态及对应的冷却天数
FOLLOWUP_ALLOWED_STATES = {
    "FOLLOWUP": 3,       # 跟进状态 → 3天冷却
    "COLD": 7,           # 冷客户 → 7天冷却
    "CLOSED_WON": 30,    # 已成交 → 30天（售后/复购）
    "CLOSED_LOST": 7,    # 丢失 → 7天再营销
}


class FollowUpGuard:
    """跟进冲突控制器

    在触发跟进前做多层检查:
      1. 状态白名单
      2. 会话锁（ConversationLock）
      3. 冷却期
    """

    @staticmethod
    def can_trigger(customer_id, state):
        """检查是否允许触发跟进

        返回:
            dict: {allowed, reason, cooldown_days}
        """
        # 1. 状态检查
        if state in FOLLOWUP_BLOCKED_STATES:
            return {
                "allowed": False,
                "reason": f"状态 {state} 禁止跟进（活跃销售中）",
                "cooldown_days": None,
            }

        # 2. 会话锁检查
        if not ConversationLock.can_followup(customer_id):
            lock_status = ConversationLock.status(customer_id)
            return {
                "allowed": False,
                "reason": "客户最近 24h 内活跃或在处理中，跳过跟进",
                "cooldown_days": None,
                "lock_status": lock_status,
            }

        # 3. 冷却期检查
        cooldown = FOLLOWUP_ALLOWED_STATES.get(state, 7)
        return {
            "allowed": True,
            "reason": f"状态 {state} 允许跟进（冷却 {cooldown} 天）",
            "cooldown_days": cooldown,
        }

    @staticmethod
    def get_blocked_states():
        """获取禁止跟进的状态列表"""
        return list(FOLLOWUP_BLOCKED_STATES)


# ═══════════════════════════════════════════════════════════
# 统一入口: stabilize()
# ═══════════════════════════════════════════════════════════

def stabilize(ctx):
    """一站式稳定层入口: 状态同步 + 置信度门控

    参数:
        ctx: dict {
            crm_state: CRM 当前状态
            ai_proposed_state: AI 提议的新状态
            confidence: AI 置信度
            action: 提议动作
            customer_id: 客户 ID
            reply: 建议回复 (可选)
        }

    返回:
        dict: {
            state: 最终状态,
            action: 最终动作,
            reply: 回复,
            safe_to_execute: bool,
            execution_level: str,
            conversation_locked: bool,
            warnings: [str],
        }
    """
    customer_id = ctx.get("customer_id", 0)
    crm_state = ctx.get("crm_state", "NEW")
    proposed_state = ctx.get("ai_proposed_state")
    confidence = ctx.get("confidence", 0.5)
    action = ctx.get("action", "reply")
    reply = ctx.get("reply", "")

    warnings = []

    # 1. 状态同步（CRM 唯一事实源）
    sync = StateSyncEngine.propose(crm_state, proposed_state)
    final_state = sync["state"]
    if sync.get("reason"):
        warnings.append(sync["reason"])

    # 2. 会话锁
    locked = ConversationLock.is_locked(customer_id)
    if locked:
        warnings.append(f"客户#{customer_id} 会话锁定中，跳过非必要操作")

    # 3. 置信度门控
    gate = ConfidenceGate.evaluate(confidence, action, final_state)

    # 4. 记录消息时间（标记客户活跃）
    ConversationLock.record_message(customer_id, direction="system")

    return {
        "state": final_state,
        "action": action if gate["allowed"] else "advisory_only",
        "confidence": round(confidence, 2),
        "reply": reply,
        "safe_to_execute": gate["allowed"] and not locked,
        "execution_level": gate["level"],
        "conversation_locked": locked,
        "state_changed": sync["changed"],
        "warnings": warnings,
        "gate_reason": gate["reason"],
    }
