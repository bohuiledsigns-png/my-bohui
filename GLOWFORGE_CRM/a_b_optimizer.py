"""V3 A/B Optimizer — 话术 A/B 测试引擎

三种话术版本，根据实际成交率自动调整选择权重。

版本策略:
  A — 价格锚+风险框架: 强调低价风险，用价格锚锁定决策
  B — 视觉效果+客流量: 强调招牌对客流量的提升效果
  C — 工厂实力+案例: 用工厂资质和成功案例建立信任
"""
import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db
from conversion_tracker import ConversionTracker


# A/B 话术版本定义
AB_SCRIPTS = {
    "A": {
        "label": "价格锚+风险框架",
        "description": "强调低价风险，用价格锚锁定决策",
        "instruction_suffix": (
            "Use price anchoring: give a standard price as reference point, "
            "then emphasize the long-term risk of cheap options. "
            "Frame it as 'most of our clients choose {anchor_price} tier'."
        ),
    },
    "B": {
        "label": "视觉效果+客流量",
        "description": "强调招牌对客流量的提升效果",
        "instruction_suffix": (
            "Focus on visual impact and foot traffic: emphasize how premium signage "
            "attracts more customers and increases brand visibility. "
            "Frame pricing as 'investment in your business image' rather than cost."
        ),
    },
    "C": {
        "label": "工厂实力+案例",
        "description": "用工厂资质和成功案例建立信任",
        "instruction_suffix": (
            "Build trust through factory expertise: reference specific certifications, "
            "production capacity, and successful case studies. "
            "Position GLOWFORGE as a professional manufacturer with proven track record."
        ),
    },
}


class ABOptimizer:
    """A/B 话术优化引擎"""

    def __init__(self):
        self._tracker = ConversionTracker()
        self._weights = self._load_weights()

    # ==================== 核心方法 ====================

    def select_version(self, state="NEW"):
        """加权随机选择 A/B/C 版本

        Args:
            state: 当前销售状态

        Returns:
            "A", "B", or "C"
        """
        weights = self._weights.get(state, {})
        w_a = weights.get("A", 1.0)
        w_b = weights.get("B", 1.0)
        w_c = weights.get("C", 1.0)
        total = w_a + w_b + w_c
        r = random.random() * total
        if r < w_a:
            return "A"
        elif r < w_a + w_b:
            return "B"
        else:
            return "C"

    def get_instruction_suffix(self, version="A"):
        """获取选定版本的 instruction 后缀"""
        script = AB_SCRIPTS.get(version, AB_SCRIPTS["A"])
        return script["instruction_suffix"]

    def get_version_label(self, version="A"):
        """获取版本中文标签"""
        script = AB_SCRIPTS.get(version, AB_SCRIPTS["A"])
        return f"[AB v{version}] {script['label']}"

    # ==================== 性能分析 ====================

    def analyze_performance(self, days=30):
        """分析 A/B 版本成交性能"""
        raw = self._tracker.get_ab_performance(days=days)
        # 按状态分组
        by_state = {}
        for row in raw:
            s = row["state"]
            if s not in by_state:
                by_state[s] = {}
            by_state[s][row["ab_version"]] = row

        # 注入当前权重
        for state, versions in by_state.items():
            for ver in ("A", "B", "C"):
                if ver in versions:
                    versions[ver]["weight"] = self._weights.get(state, {}).get(ver, 1.0)

        return by_state

    # ==================== 权重调优 ====================

    def adjust_weights(self, days=30, min_samples=15):
        """核心优化逻辑：根据成交率调整权重

        算法:
          - 每个状态内，计算各版本的成交率
          - 找出最优版本（最高成交率，且 >= min_samples 样本）
          - 最优版本权重 +0.2（上限 2.0）
          - 最差版本权重 -0.1（下限 0.3）
          - 如果样本不足或差异不显著，保留当前权重

        Returns:
            dict: {changes_made, new_weights, summary}
        """
        raw = self._tracker.get_ab_performance(days=days)
        changes_made = 0
        summary_parts = []

        # 按状态分组
        by_state = {}
        for row in raw:
            s = row["state"]
            if s not in by_state:
                by_state[s] = {}
            by_state[s][row["ab_version"]] = row

        for state, versions in by_state.items():
            # 只分析有足够样本的版本
            viable = {v: d for v, d in versions.items()
                      if d["total_trials"] >= min_samples and d["conversion_rate"] > 0}
            if len(viable) < 2:
                continue

            # 找最优和最差
            best_ver = max(viable, key=lambda v: viable[v]["conversion_rate"])
            worst_ver = min(viable, key=lambda v: viable[v]["conversion_rate"])
            best_rate = viable[best_ver]["conversion_rate"]
            worst_rate = viable[worst_ver]["conversion_rate"]

            # 只有差异 > 5% 才调权
            if best_rate - worst_rate < 0.05:
                continue

            old_best = self._weights.get(state, {}).get(best_ver, 1.0)
            old_worst = self._weights.get(state, {}).get(worst_ver, 1.0)

            new_best = min(2.0, old_best + 0.2)
            new_worst = max(0.3, old_worst - 0.1)

            self._set_weight(state, best_ver, new_best, "auto_optimize")
            self._set_weight(state, worst_ver, new_worst, "auto_optimize")

            changes_made += 2
            summary_parts.append(
                f"{state}: {best_ver}↑{new_best:.1f}({best_rate:.0%}) {worst_ver}↓{new_worst:.1f}({worst_rate:.0%})"
            )

        self._save_weights()
        return {
            "changes_made": changes_made,
            "new_weights": self._weights,
            "summary": "; ".join(summary_parts) or "No significant differences found",
        }

    # ==================== 权重管理 ====================

    def get_current_weights(self):
        """获取当前权重"""
        return self._weights

    def set_manual_weight(self, state, version, weight):
        """手动设置权重"""
        weight = max(0.3, min(2.0, weight))
        self._set_weight(state, version, weight, "manual_adjust")
        self._save_weights()

    def reset_weights(self):
        """重置所有权重为 1.0"""
        self._weights = {}
        conn = get_db()
        conn.execute("UPDATE v3_ab_test_results SET weight=1.0")
        conn.commit()
        conn.close()
        self._log_weight_change("all", "all", "reset", "reset", "manual_reset", "system")

    # ==================== 内部方法 ====================

    def _set_weight(self, state, version, weight, reason="auto_optimize"):
        """设置单个版本权重"""
        if state not in self._weights:
            self._weights[state] = {}
        old = self._weights[state].get(version, 1.0)
        self._weights[state][version] = weight

        conn = get_db()
        conn.execute(
            """INSERT INTO v3_ab_test_results (state, ab_version, weight)
               VALUES (?,?,?)
               ON CONFLICT(state, ab_version) DO UPDATE SET weight=excluded.weight,
               updated_at=CURRENT_TIMESTAMP""",
            (state, version, weight)
        )
        conn.commit()
        conn.close()

        self._log_weight_change("ab_weight", f"{state}/{version}", str(old), str(weight), reason, "system")

    def _load_weights(self):
        """从数据库加载权重"""
        weights = {}
        conn = get_db()
        rows = conn.execute(
            "SELECT state, ab_version, weight FROM v3_ab_test_results"
        ).fetchall()
        conn.close()
        for r in rows:
            s = r["state"]
            if s not in weights:
                weights[s] = {}
            weights[s][r["ab_version"]] = r["weight"]
        return weights

    def _save_weights(self):
        """持久化权重到数据库（已通过 _set_weight 实时写入）"""
        pass  # weights saved per-operation in _set_weight

    def _log_weight_change(self, weight_type, weight_key, old_value, new_value, reason, triggered_by):
        """记录权重变更到审计日志"""
        conn = get_db()
        conn.execute(
            "INSERT INTO v3_weight_history (weight_type, weight_key, old_value, new_value, reason, triggered_by) VALUES (?,?,?,?,?,?)",
            (weight_type, weight_key, old_value, new_value, reason, triggered_by)
        )
        conn.commit()
        conn.close()


# ==================== 快捷入口 ====================

optimizer = ABOptimizer()


def select_ab_version(state="NEW"):
    return optimizer.select_version(state)


def get_ab_suffix(version="A"):
    return optimizer.get_instruction_suffix(version)
