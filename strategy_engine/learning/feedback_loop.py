"""Feedback Loop — 策略学习循环

每日自动分析策略效果，驱动策略优化。

复用:
  - V7 RevenueFeedbackLoop 的历史数据
  - strategy_state.json 的过往策略记录
"""
import logging
import json
import os
import shutil
from datetime import datetime

logger = logging.getLogger("feedback_loop")

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "strategy_state.json",
)

BACKUP_DIR = os.path.join(
    os.path.dirname(STATE_PATH), "backups",
)


def _load_state():
    """从 strategy_state.json 加载历史状态"""
    try:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load state: {e}")
    return {"learning_state": {}, "runs": []}


def _save_state(state):
    """写入 strategy_state.json（原子写入 + 自动备份）"""
    try:
        # 自动备份旧状态
        if os.path.exists(STATE_PATH):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            backup_name = (
                f"strategy_state.json."
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            )
            shutil.copy2(STATE_PATH, os.path.join(BACKUP_DIR, backup_name))
    except OSError:
        pass

    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception as e:
        logger.warning(f"Failed to save state: {e}")


class FeedbackLoop:
    """策略学习循环"""

    @staticmethod
    def run_learning_cycle(dry_run=True):
        """执行完整学习周期

        流程:
          1. 加载过往策略状态
          2. 调用 V2 RevenueFeedbackLoop 获取洞察
          3. 对比分析当前策略效果
          4. 建议策略权重调整
          5. 非 dry_run 时写入学习结果

        返回:
            dict: { cycle_date, dry_run, v2_insights, learned_adjustments, recommendations }
        """
        state = _load_state()
        v2_insights = {}
        adjustments = []

        # 尝试获取 V2 洞察
        try:
            from ai_engine.revenue_feedback_loop import RevenueFeedbackLoop
            loop = RevenueFeedbackLoop()
            v2_insights = loop.get_insights(days=30)
        except Exception as e:
            logger.warning(f"V2 RevenueFeedbackLoop unavailable: {e}")

        # 基于历史记录分析效果
        effectiveness = FeedbackLoop.analyze_effectiveness(state)

        # 学习权重建议
        if v2_insights:
            suggestions = FeedbackLoop._derive_adjustments(v2_insights, effectiveness)
            adjustments.extend(suggestions)

        result = {
            "cycle_date": datetime.now().isoformat(),
            "dry_run": dry_run,
            "v2_insights": v2_insights,
            "strategy_effectiveness": effectiveness,
            "learned_adjustments": adjustments,
            "recommendations": FeedbackLoop._generate_recommendations(
                v2_insights, effectiveness
            ),
        }

        if not dry_run:
            state.setdefault("learning_state", {})
            state["learning_state"]["last_learning_cycle"] = result["cycle_date"]
            state["learning_state"]["weight_adjustments"] = (
                state["learning_state"].get("weight_adjustments", []) + adjustments
            )
            state["learning_state"]["effectiveness_history"] = (
                state["learning_state"].get("effectiveness_history", [])
            )
            state["learning_state"]["effectiveness_history"].append({
                "date": result["cycle_date"],
                "score": effectiveness.get("effectiveness_score", 0),
            })
            _save_state(state)

        return result

    @staticmethod
    def analyze_effectiveness(state=None):
        """分析当前策略效果"""
        if state is None:
            state = _load_state()

        learning = state.get("learning_state", {})
        history = learning.get("effectiveness_history", [])

        # 基于历史趋势评估
        recent = history[-5:] if len(history) >= 5 else history
        trend = 0
        if len(recent) >= 2:
            scores = [h.get("score", 0) for h in recent]
            trend = scores[-1] - scores[0]

        return {
            "effectiveness_score": 50 + trend * 10,
            "trend_direction": "improving" if trend > 0 else "declining" if trend < 0 else "stable",
            "history_length": len(history),
            "insufficient_data": len(history) < 3,
        }

    @staticmethod
    def _derive_adjustments(v2_insights, effectiveness):
        """从洞察推导策略调整"""
        adjustments = []
        best_countries = v2_insights.get("best_countries", [])
        if best_countries:
            adjustments.append({
                "area": "market_focus",
                "current_setting": "balanced",
                "suggested_setting": best_countries[0].get("source", "US"),
                "expected_impact": "提高高转化市场预算分配",
            })

        best_products = v2_insights.get("best_products", [])
        if best_products:
            adjustments.append({
                "area": "product_focus",
                "current_setting": "broad",
                "suggested_setting": best_products[0].get("source", ""),
                "expected_impact": "集中推广高利润产品",
            })

        return adjustments

    @staticmethod
    def _generate_recommendations(v2_insights, effectiveness):
        """生成可执行建议"""
        recs = []
        if effectiveness.get("insufficient_data"):
            recs.append("数据不足，建议累积3天以上运行记录")
        if effectiveness.get("trend_direction") == "declining":
            recs.append("策略效果下降，建议检查市场/产品评分权重")
        if v2_insights.get("best_countries"):
            recs.append(f"考虑增加 {v2_insights['best_countries'][0].get('source', '')} 市场投入")
        return recs

    @staticmethod
    def update_weights(insights):
        """建议评分权重更新（预留接口）"""
        return []
