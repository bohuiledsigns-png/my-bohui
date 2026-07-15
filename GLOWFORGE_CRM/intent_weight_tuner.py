"""V3 Intent Weight Tuner — 意图权重自动调优

根据实际意图→成交概率数据自动调整 _INTENT_CONVERSION_BONUS。

算法:
  - 对每个意图，计算实际成交率 vs 整体基准成交率
  - 相对性能 = 实际 / 基准
  - 新权重 = 默认值 + int((相对性能 - 1.0) * 50)
  - 结果限制在 INTENT_WEIGHT_RANGES 定义的 min/max 范围内
  - 如果相对性能在 0.9-1.1x 范围内则保留默认值
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db
from conversion_tracker import ConversionTracker

# JSON 持久化路径
_V3_WEIGHTS_PATH = os.path.join(BASE_DIR, "v3_intent_weights.json")

# 意图权重范围配置
INTENT_WEIGHT_RANGES = {
    "询价": {"min": -10, "max": 20, "default": 5},
    "比价": {"min": -20, "max": 5, "default": -5},
    "问工艺": {"min": -10, "max": 10, "default": 0},
    "要样品": {"min": -5, "max": 15, "default": 5},
    "要目录": {"min": -10, "max": 10, "default": 0},
    "问交期": {"min": -5, "max": 15, "default": 5},
    "下单": {"min": 5, "max": 30, "default": 20},
    "售后": {"min": -30, "max": 0, "default": -15},
    "合作": {"min": -5, "max": 20, "default": 10},
    "跟进": {"min": -10, "max": 10, "default": 0},
}


class IntentWeightTuner:
    """意图权重自动调优器"""

    def __init__(self):
        self._tracker = ConversionTracker()
        self._loaded_weights = self._load_json_weights()

    # ==================== 分析 ====================

    def analyze_intent_performance(self, days=60):
        """分析各意图的成交性能"""
        raw = self._tracker.get_intent_performance(days=days)
        # 计算整体基准成交率
        total_won = sum(r["won_count"] for r in raw)
        total_occ = sum(r["total_occurrences"] for r in raw)
        baseline_rate = total_won / total_occ if total_occ > 0 else 0

        results = []
        for r in raw:
            intent = r["intent"]
            actual_rate = r["conversion_rate"]
            relative = actual_rate / baseline_rate if baseline_rate > 0 else 1.0
            ranges = INTENT_WEIGHT_RANGES.get(intent, {"min": -10, "max": 10, "default": 0})
            results.append({
                "intent": intent,
                "total_occurrences": r["total_occurrences"],
                "won_count": r["won_count"],
                "conversion_rate": actual_rate,
                "baseline_rate": baseline_rate,
                "relative_performance": round(relative, 4),
                "current_weight": self._loaded_weights.get(intent, ranges["default"]),
                "default_weight": ranges["default"],
            })

        return {"baseline_rate": baseline_rate, "results": results}

    def compute_optimal_weights(self, min_samples=15):
        """核心算法：计算最优意图权重

        Args:
            min_samples: 最小样本数要求

        Returns:
            dict: {intent: new_weight}
        """
        analysis = self.analyze_intent_performance()
        baseline_rate = analysis["baseline_rate"]
        optimal = {}

        for r in analysis["results"]:
            intent = r["intent"]
            if r["total_occurrences"] < min_samples:
                # 样本不足，保留当前值
                optimal[intent] = r["current_weight"]
                continue

            ranges = INTENT_WEIGHT_RANGES.get(intent, {"min": -10, "max": 10, "default": 0})
            relative = r["relative_performance"]

            # 如果在 0.9-1.1x 范围内，保留默认值
            if 0.9 <= relative <= 1.1:
                new_weight = ranges["default"]
            else:
                # 新权重 = 默认值 + (相对性能 - 1.0) * 50
                new_weight = ranges["default"] + int((relative - 1.0) * 50)

            # 限制在允许范围内
            new_weight = max(ranges["min"], min(ranges["max"], new_weight))
            optimal[intent] = new_weight

        return optimal

    # ==================== 应用 ====================

    def update_weights(self, dry_run=False):
        """将优化后的权重应用到 revenue_engine._INTENT_CONVERSION_BONUS

        Args:
            dry_run: 如果是 True，只返回变更预览不实际写入

        Returns:
            dict: {changes_made, summary, changes: [{intent, old, new}]}
        """
        optimal = self.compute_optimal_weights()
        changes = []
        changes_made = 0

        # 获取当前值
        try:
            import revenue_engine
            current = dict(revenue_engine._INTENT_CONVERSION_BONUS)
        except Exception:
            current = {}

        for intent, new_weight in optimal.items():
            ranges = INTENT_WEIGHT_RANGES.get(intent, {"min": -10, "max": 10, "default": 0})
            old_weight = current.get(intent, ranges["default"])

            if old_weight != new_weight:
                changes.append({
                    "intent": intent,
                    "old": old_weight,
                    "new": new_weight,
                })
                changes_made += 1

                if not dry_run:
                    # 更新 revenue_engine
                    try:
                        revenue_engine._INTENT_CONVERSION_BONUS[intent] = new_weight
                    except Exception:
                        pass

                    # 更新数据库
                    conn = get_db()
                    conn.execute(
                        """INSERT INTO v3_intent_conversion_stats
                           (intent, current_weight, optimized_weight, last_updated_at)
                           VALUES (?,?,?,CURRENT_TIMESTAMP)
                           ON CONFLICT(intent) DO UPDATE SET
                           current_weight=excluded.current_weight,
                           optimized_weight=excluded.optimized_weight,
                           last_updated_at=CURRENT_TIMESTAMP""",
                        (intent, new_weight, new_weight)
                    )
                    conn.commit()
                    conn.close()

                    # 审计日志
                    conn = get_db()
                    conn.execute(
                        "INSERT INTO v3_weight_history (weight_type, weight_key, old_value, new_value, reason, triggered_by) VALUES (?,?,?,?,?,?)",
                        ("intent_bonus", intent, str(old_weight), str(new_weight), "auto_optimize", "system")
                    )
                    conn.commit()
                    conn.close()

        # 持久化到 JSON
        if not dry_run and changes_made > 0:
            self._loaded_weights.update(optimal)
            self._save_json_weights()

        summary_parts = [f"{c['intent']}: {c['old']}→{c['new']}" for c in changes]
        return {
            "changes_made": changes_made,
            "summary": "; ".join(summary_parts) or "No changes needed",
            "changes": changes,
        }

    # ==================== 权重管理 ====================

    def get_current_weights(self):
        """获取当前 intent 权重（从 revenue_engine 读取）"""
        try:
            import revenue_engine
            return dict(revenue_engine._INTENT_CONVERSION_BONUS)
        except Exception:
            return {}

    def set_manual_weight(self, intent, weight):
        """手动设置单个意图权重"""
        ranges = INTENT_WEIGHT_RANGES.get(intent, {"min": -10, "max": 10, "default": 0})
        weight = max(ranges["min"], min(ranges["max"], weight))

        try:
            import revenue_engine
            old = revenue_engine._INTENT_CONVERSION_BONUS.get(intent, ranges["default"])
            revenue_engine._INTENT_CONVERSION_BONUS[intent] = weight
        except Exception:
            old = ranges["default"]

        self._loaded_weights[intent] = weight
        self._save_json_weights()

        conn = get_db()
        conn.execute(
            "INSERT INTO v3_weight_history (weight_type, weight_key, old_value, new_value, reason, triggered_by) VALUES (?,?,?,?,?,?)",
            ("intent_bonus", intent, str(old), str(weight), "manual_adjust", "user")
        )
        conn.commit()
        conn.close()

    def reset_weights(self):
        """重置所有权重为默认值"""
        try:
            import revenue_engine
            for intent, ranges in INTENT_WEIGHT_RANGES.items():
                old = revenue_engine._INTENT_CONVERSION_BONUS.get(intent, ranges["default"])
                if old != ranges["default"]:
                    revenue_engine._INTENT_CONVERSION_BONUS[intent] = ranges["default"]
                    conn = get_db()
                    conn.execute(
                        "INSERT INTO v3_weight_history (weight_type, weight_key, old_value, new_value, reason, triggered_by) VALUES (?,?,?,?,?,?)",
                        ("intent_bonus", intent, str(old), str(ranges["default"]), "manual_reset", "user")
                    )
                    conn.commit()
                    conn.close()
        except Exception:
            pass

        self._loaded_weights = {}
        if os.path.exists(_V3_WEIGHTS_PATH):
            os.remove(_V3_WEIGHTS_PATH)

    # ==================== 持久化 ====================

    def _load_json_weights(self):
        """从 JSON 文件加载优化后的权重"""
        if os.path.exists(_V3_WEIGHTS_PATH):
            try:
                with open(_V3_WEIGHTS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_json_weights(self):
        """持久化权重到 JSON 文件"""
        with open(_V3_WEIGHTS_PATH, "w", encoding="utf-8") as f:
            json.dump(self._loaded_weights, f, ensure_ascii=False, indent=2)


# ==================== 快捷入口 ====================

tuner = IntentWeightTuner()


def load_persisted_intent_weights():
    """启动时调用，加载优化后的意图权重到 revenue_engine"""
    try:
        import revenue_engine
        weights = tuner._load_json_weights()
        if weights:
            for intent, weight in weights.items():
                revenue_engine._INTENT_CONVERSION_BONUS[intent] = weight
        return True
    except Exception:
        return False
