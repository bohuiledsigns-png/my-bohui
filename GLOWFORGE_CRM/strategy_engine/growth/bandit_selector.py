"""Multi-Armed Bandit Selector — 自动选择最优策略

系统自动决定每个策略的权重：
  - 高 ROI → 更高投放权重
  - 低 ROI → 降低权重（自动淘汰）
  - 新策略 → 探索空间（epsilon 机制）

算法: ε-greedy + 置信度上界
  exploit(85%): 选当前最优
  explore(15%): 探索未充分测试的组合
"""
import logging
import random
from datetime import datetime

logger = logging.getLogger("growth.bandit_selector")

EPSILON = 0.15          # 探索率
MIN_SAMPLES = 3          # 最小样本量才可信
CONFIDENCE_THRESHOLD = 0.6  # 置信度阈值


class MultiArmedBandit:
    """多臂赌博机选择器"""

    @staticmethod
    def select_strategies(experiments, historical_results=None, n=5):
        """选择最优策略

        参数:
            experiments: GrowthExperimentEngine 生成的实验列表
            historical_results: 各策略的历史 ROI 数据
            n: 返回策略数

        返回:
            dict: { selected_strategies, bandit_state, summary }
        """
        if not experiments:
            return {
                "selected_strategies": [],
                "bandit_state": {"weights": {}, "exploration_rate": EPSILON},
                "summary": {"selected": 0, "exploit_count": 0, "explore_count": 0},
            }

        # 构建策略 key → 实验 映射
        strategy_map = {}
        for exp in experiments:
            key = MultiArmedBandit._strategy_key(exp)
            strategy_map[key] = exp

        # 加载历史表现
        histories = historical_results or {}
        all_keys = list(strategy_map.keys())

        # ε-greedy 决策
        selected = []
        exploit_count = 0
        explore_count = 0
        used_keys = set()

        for _ in range(min(n, len(all_keys))):
            remaining = [k for k in all_keys if k not in used_keys]
            if not remaining:
                break

            if random.random() < EPSILON and len(remaining) > 1:
                # ── Explore: 选历史样本最少或未测试的 ──
                key = MultiArmedBandit._explore_choice(remaining, histories)
                explore_count += 1
            else:
                # ── Exploit: 选预期 ROI 最高的 ──
                key = MultiArmedBandit._exploit_choice(remaining, histories, strategy_map)
                exploit_count += 1

            used_keys.add(key)
            exp = strategy_map[key]
            hist = histories.get(key, {})

            selected.append({
                "strategy_key": key,
                "market": exp["market"],
                "product": exp["product"],
                "angle_id": exp["angle_id"],
                "angle_name": exp["angle_name"],
                "pricing_tier": exp["pricing_tier"],
                "score": exp["score"],
                "expected_roi": exp["expected_roi"],
                "historical_roi": hist.get("avg_roi", None),
                "samples": hist.get("samples", 0),
                "confidence": MultiArmedBandit._calculate_confidence(hist),
                "selection_mode": "exploit" if key in [s.get("strategy_key") for s in selected[:0]] else ("explore" if key not in [s.get("strategy_key") for s in selected] else "exploit"),
            })

        # 修正 selection_mode（上面写法有逻辑 bug）
        selected_sorted = []
        for i, s in enumerate(selected):
            s["selection_mode"] = "exploit" if i < (len(selected) - explore_count) else "explore"
            selected_sorted.append(s)

        # 权重计算
        weights = MultiArmedBandit._calculate_weights(selected_sorted, histories)

        return {
            "selected_strategies": selected_sorted,
            "bandit_state": {
                "weights": weights,
                "exploration_rate": EPSILON,
                "total_trials": sum(h.get("samples", 0) for h in histories.values()) if histories else 0,
            },
            "summary": {
                "selected": len(selected_sorted),
                "exploit_count": exploit_count,
                "explore_count": explore_count,
            },
        }

    @staticmethod
    def _strategy_key(exp):
        """生成策略唯一键"""
        return f"{exp['market']}|{exp['product']}|{exp['angle_id']}|{exp['pricing_tier']}"

    @staticmethod
    def _explore_choice(remaining, histories):
        """探索模式: 选样本最少或从未测试的策略"""
        untested = [k for k in remaining if k not in histories]
        if untested:
            return random.choice(untested)

        # 选样本最少的
        return min(remaining, key=lambda k: histories.get(k, {}).get("samples", 0))

    @staticmethod
    def _exploit_choice(remaining, histories, strategy_map):
        """利用模式: 选期望收益最高的"""
        def expected_value(key):
            exp = strategy_map[key]
            base = exp.get("expected_roi", 0)
            hist = histories.get(key, {})
            if hist.get("samples", 0) >= MIN_SAMPLES:
                # 加权平均: 历史 60% + 理论 40%
                hist_roi = hist.get("avg_roi", 0)
                return 0.6 * hist_roi + 0.4 * base
            return base

        return max(remaining, key=expected_value)

    @staticmethod
    def _calculate_confidence(history):
        """计算置信度 (基于样本量)"""
        if not history:
            return 0.0
        samples = history.get("samples", 0)
        if samples < MIN_SAMPLES:
            return round(samples / MIN_SAMPLES, 2)
        # 用样本量估算置信度，上限 0.99
        return round(min(1 - 1 / (samples + 1), 0.99), 2)

    @staticmethod
    def _calculate_weights(strategies, histories):
        """计算各策略的投放权重 (softmax-like)"""
        scores = []
        for s in strategies:
            key = s["strategy_key"]
            hist = histories.get(key, {})
            if hist.get("samples", 0) >= MIN_SAMPLES:
                raw = hist.get("avg_roi", 0)
            else:
                raw = s.get("expected_roi", 0)
            scores.append(max(raw, 0.01))

        total = sum(scores)
        if total <= 0:
            return {s["strategy_key"]: round(1.0 / len(strategies), 3) for s in strategies}

        return {
            s["strategy_key"]: round(score / total, 3)
            for s, score in zip(strategies, scores)
        }

    @staticmethod
    def update_with_result(bandit_state, strategy_key, roi_result):
        """用新结果更新赌博机状态"""
        weights = bandit_state.get("weights", {})
        if strategy_key in weights:
            # 简单调整: ROI > 预期则增权，否则减权
            current = weights[strategy_key]
            if roi_result > 0:
                weights[strategy_key] = round(min(current * 1.1, 0.5), 3)
            else:
                weights[strategy_key] = round(current * 0.9, 3)

        return {"weights": weights, "exploration_rate": EPSILON}

    @staticmethod
    def get_best_strategy(bandit_state):
        """从当前状态获取最优策略"""
        weights = bandit_state.get("weights", {})
        if not weights:
            return None
        best_key = max(weights, key=weights.get)
        return {
            "strategy_key": best_key,
            "weight": weights[best_key],
            "confidence": min(weights[best_key] * 2, 0.95),
        }
