"""Agent Coordinator — 多 Agent 协调层

Phase 2 控制面核心组件，解决 3 层 Agent 无协调的问题：
  - Layer A: multi_agent_team.py (区域代理)
  - Layer B: ai_engine/agents/ (竞争个性代理)
  - Layer C: ai_overlay/multi_agent_brain.py (协作代理)

职责:
  1. 每客户互斥锁 — 防止不同 Agent 同时操作同一客户
  2. 主导 Agent 选举 — 基于状态/意图选择谁主导本次交互
  3. 价格 Oracle — 冻结 _PRICE_ANCHORS 快照，防止报价污染

所有方法 try/except 包裹，模块缺失时优雅降级。
"""
import json
import logging
import threading
import time

logger = logging.getLogger("glowforge.agent_coordinator")

_LOCK_TIMEOUT = 1800.0  # 30 分钟自动超时
_LOCK_CLEANUP_INTERVAL = 300.0  # 每 5 分钟清理过期锁


class _AgentLock:
    """每客户锁的内部状态"""
    __slots__ = ("agent_id", "acquired_at", "timeout")

    def __init__(self, agent_id, timeout=None):
        self.agent_id = agent_id
        self.acquired_at = time.time()
        self.timeout = timeout or _LOCK_TIMEOUT

    @property
    def expired(self):
        return (time.time() - self.acquired_at) > self.timeout


# 全局锁存储（进程级）
_customer_locks = {}
_locks_lock = threading.Lock()
_last_cleanup = time.time()

# 主导 Agent 选择规则
_LEAD_AGENT_RULES = [
    # (state_pattern, intent_pattern, agent_id)
    # 精确匹配优先
    ("NEGOTIATING", None, "closer_agent"),
    ("HOT", None, "closer_agent"),
    ("CLOSING", None, "closer_agent"),
    ("CLOSED_WON", None, "closer_agent"),
    ("COLD", None, "soft_seller_agent"),
    ("NEW", None, "consultant_agent"),
    ("INTERESTED", None, "consultant_agent"),
    ("QUALIFYING", None, "consultant_agent"),
    ("PRICING", None, "hunter_agent"),
    ("REQUESTED_PRICE", None, "hunter_agent"),
    # 依意图覆盖
    (None, "问工艺", "technical_agent"),
    (None, "要样品", "technical_agent"),
    (None, "售后", "technical_agent"),
    (None, "比价", "negotiator"),
    (None, "下单", "closer_agent"),
    (None, "问交期", "consultant_agent"),
]

# 安全默认
_DEFAULT_LEAD_AGENT = "consultant_agent"


class AgentCoordinator:
    """Agent 协调器 — 每客户锁 + 主导选举 + 价格快照"""

    def __init__(self, registry=None):
        self._registry = registry

    def _get_registry(self):
        if self._registry is None:
            try:
                from safety.state_registry import StateRegistry
                self._registry = StateRegistry()
            except ImportError:
                self._registry = None
        return self._registry

    # ── 每客户锁 ──

    def lock(self, customer_id, agent_id):
        """获取对某客户的操作锁

        返回:
            bool: True 获取成功，False 已被其他 Agent 锁定或锁获取失败
        """
        global _last_cleanup
        try:
            # 定期清理过期锁
            now = time.time()
            if now - _last_cleanup > _LOCK_CLEANUP_INTERVAL:
                self.release_expired_locks()
                _last_cleanup = now

            with _locks_lock:
                existing = _customer_locks.get(customer_id)
                if existing is None:
                    _customer_locks[customer_id] = _AgentLock(agent_id)
                    return True
                if existing.expired or existing.agent_id == agent_id:
                    # 过期锁或同一 Agent 续期 → 重新获取
                    _customer_locks[customer_id] = _AgentLock(agent_id)
                    return True
                # 被其他 Agent 持有
                logger.warning(
                    "[Coordinator] 锁冲突: 客户 %s 被 %s 锁定（%s 请求）",
                    customer_id, existing.agent_id, agent_id,
                )
                return False
        except Exception as e:
            logger.warning("[Coordinator] lock 异常（放行）: %s", e)
            return True  # 降级：允许通过

    def unlock(self, customer_id):
        """释放客户的操作锁"""
        try:
            with _locks_lock:
                _customer_locks.pop(customer_id, None)
            return True
        except Exception:
            return False

    def get_current_agent(self, customer_id):
        """查询当前持有某客户锁的 Agent"""
        try:
            with _locks_lock:
                lock = _customer_locks.get(customer_id)
                if lock and not lock.expired:
                    return lock.agent_id
                if lock and lock.expired:
                    _customer_locks.pop(customer_id, None)
                return None
        except Exception:
            return None

    def release_expired_locks(self):
        """清理所有过期锁"""
        try:
            now = time.time()
            with _locks_lock:
                expired = [
                    cid for cid, lock in _customer_locks.items()
                    if (now - lock.acquired_at) > lock.timeout
                ]
                for cid in expired:
                    _customer_locks.pop(cid, None)
                if expired:
                    logger.info("[Coordinator] 清理 %d 个过期锁", len(expired))
        except Exception:
            pass

    def get_active_sessions(self):
        """返回当前活跃会话列表（监控用）"""
        try:
            self.release_expired_locks()
            with _locks_lock:
                return [
                    {
                        "customer_id": cid,
                        "agent_id": lock.agent_id,
                        "elapsed_seconds": int(time.time() - lock.acquired_at),
                    }
                    for cid, lock in _customer_locks.items()
                ]
        except Exception:
            return []

    # ── 主导 Agent 选举 ──

    def select_lead_agent(self, customer_id, intent="", lead_state=""):
        """基于状态 + 意图选举主导 Agent

        参数:
            customer_id: 客户ID（仅用于日志）
            intent: 意图分类（中文，如 "询价"/"比价"/"问工艺"）
            lead_state: 客户 lead_state（如 "NEW"/"NEGOTIATING"）

        返回:
            str: Agent ID（如 "consultant_agent", "hunter_agent"）
        """
        try:
            # Pass 1: 意图优先匹配（intent 比 state 更具体）
            for state_pattern, intent_pattern, agent_id in _LEAD_AGENT_RULES:
                if intent_pattern and intent_pattern == intent:
                    if state_pattern is None or state_pattern == lead_state:
                        return agent_id

            # Pass 2: 仅状态匹配
            for state_pattern, intent_pattern, agent_id in _LEAD_AGENT_RULES:
                if intent_pattern is None and state_pattern == lead_state:
                    return agent_id

            return _DEFAULT_LEAD_AGENT
        except Exception:
            return _DEFAULT_LEAD_AGENT

    # ── 价格 Oracle ──

    def get_price_oracle(self, customer_id):
        """冻结当前 _PRICE_ANCHORS 返回不可变快照

        解决 5 个定价引擎全局突变 _PRICE_ANCHORS 的问题。
        返回的快照在客户会话期间保持不变。

        返回:
            dict: 深度复制的价格锚点（空 dict = 降级）
        """
        try:
            from sales_executor import _PRICE_ANCHORS
            snapshot = json.loads(json.dumps(_PRICE_ANCHORS))
            # 记录到 WAL
            registry = self._get_registry()
            if registry:
                current_agent = self.get_current_agent(customer_id)
                registry.register_action(customer_id, "price_oracle", {
                    "snapshot_keys": list(snapshot.keys()),
                    "agent": current_agent,
                })
            return snapshot
        except (ImportError, Exception) as e:
            logger.warning("[Coordinator] 价格 Oracle 降级: %s", e)
            return {}

    # ── Agent 动作记录 ──

    def record_agent_action(self, customer_id, agent_id, action_type, price=None):
        """记录带 Agent 身份的动作到 WAL

        参数:
            customer_id: 客户 ID
            agent_id: Agent 身份标识
            action_type: 动作类型
            price: 报价金额（如有）
        """
        try:
            registry = self._get_registry()
            if registry:
                registry.register_action(customer_id, action_type, {
                    "source_agent": agent_id,
                    "price": price,
                })
        except Exception:
            pass
