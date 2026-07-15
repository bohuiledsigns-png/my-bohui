"""Self-Learning Loop — 自进化循环

系统每天自动:
  1. 评估上一轮实验结果
  2. 更新策略权重（Bandit 状态）
  3. 淘汰低效组合
  4. 生成新实验
  5. 持久化增长状态

循环: Experiment → Execution → Result → Analysis → New Strategy
"""
import json
import logging
import os
import shutil
from datetime import datetime, timedelta

logger = logging.getLogger("growth.self_learning_loop")


def _parse_dt(s):
    """兼容 Python 3.6 的 ISO 时间解析"""
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

# ── 状态文件路径 ──
GROWTH_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "growth_state.json",
)

# ── 学习配置 ──
MAX_HISTORY_PER_EXPERIMENT = 30    # 每个实验最多保存 N 条历史
MIN_SAMPLE_FOR_DECISION = 3         # 最少 N 个样本才能做决策
BANDIT_WEIGHT_DECAY = 0.95          # 历史权重衰减
EXPERIMENT_PRUNE_AGE_DAYS = 21      # 超过 N 天未活动的实验自动淘汰


class SelfLearningLoop:
    """自进化循环 — 增长系统的学习引擎"""

    @staticmethod
    def run_growth_cycle(
        strategy_report=None,
        roi_data=None,
        dry_run=True,
    ):
        """运行完整自进化循环

        参数:
            strategy_report: StrategyEngine.run_full_analysis() 输出
            roi_data: ROIEngine.calculate_roi() 输出
            dry_run: 预览模式

        返回:
            dict: { cycle_results, state_changes, growth_state }
        """
        # ── 1. 加载当前状态 ──
        growth_state = SelfLearningLoop._load_state()

        cycle_number = growth_state.get("cycle_number", 0) + 1
        logger.info(f"Growth cycle #{cycle_number}")

        # ── 2. 评估历史实验 ──
        evaluation = SelfLearningLoop._evaluate_experiments(growth_state, roi_data)
        logger.info(
            f"  Evaluated: {evaluation['total_evaluated']} experiments"
            f" | Improved: {evaluation['improved']}"
            f" | Declined: {evaluation['declined']}"
        )

        # ── 3. 更新 Bandit 权重 ──
        bandit_update = SelfLearningLoop._update_bandit_weights(
            growth_state, evaluation, roi_data,
        )
        logger.info(
            f"  Bandit: {bandit_update['total_strategies']} strategies weighted"
        )

        # ── 4. 淘汰低效组合 ──
        pruned = SelfLearningLoop._prune_stale_experiments(growth_state)
        if pruned["removed"] > 0:
            logger.info(f"  Pruned {pruned['removed']} stale experiments")

        # ── 5. 生成新实验 ──
        from strategy_engine.growth.experiment_engine import GrowthExperimentEngine
        from strategy_engine.growth.angle_generator import CreativeAngleGenerator

        angle_data = CreativeAngleGenerator.generate_angles(limit=8)
        new_experiments = GrowthExperimentEngine.generate_experiments(
            market_data=strategy_report.get("market_strategy") if strategy_report else None,
            product_data=strategy_report.get("product_strategy") if strategy_report else None,
            pricing_data=strategy_report.get("pricing_strategy") if strategy_report else None,
            angle_data=angle_data,
            growth_state=growth_state,
            dry_run=dry_run,
        )
        logger.info(
            f"  New experiments: {new_experiments['summary']['experiments_generated']}"
        )

        # ── 6. 更新状态 ──
        state_changes = SelfLearningLoop._update_state(
            growth_state, evaluation, bandit_update, new_experiments,
            pruned, cycle_number, dry_run,
        )

        # ── 7. 持久化 ──
        if not dry_run:
            SelfLearningLoop._save_state(growth_state)
            state_changes["saved"] = True
            logger.info("  Growth state saved")

        # ── 8. 注入新实验到市场扩张 ──
        expansion_injections = SelfLearningLoop._generate_expansion_signals(
            growth_state, roi_data,
        )

        return {
            "cycle_number": cycle_number,
            "evaluation": evaluation,
            "bandit_update": bandit_update,
            "new_experiments": new_experiments,
            "pruned": pruned,
            "expansion_signals": expansion_injections,
            "state_changes": state_changes,
            "growth_state": growth_state if not dry_run else {
                "cycle_number": cycle_number,
                "_dry_run_preview": True,
            },
        }

    @staticmethod
    def _load_state():
        """加载 growth_state.json"""
        if os.path.exists(GROWTH_STATE_PATH):
            try:
                with open(GROWTH_STATE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load growth state: {e}")
        return {
            "version": "3.2.0",
            "cycle_number": 0,
            "experiment_history": {},
            "bandit_weights": {},
            "archived_experiments": [],
            "market_attempts": [],
            "last_cycle_at": None,
            "created_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _save_state(state):
        """持久化 growth_state.json（原子写入 + 自动备份）"""
        state["last_updated"] = datetime.now().isoformat()
        try:
            # 自动备份旧状态
            if os.path.exists(GROWTH_STATE_PATH):
                backup_dir = os.path.join(
                    os.path.dirname(GROWTH_STATE_PATH), "backups",
                )
                os.makedirs(backup_dir, exist_ok=True)
                backup_name = (
                    f"growth_state.json."
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                )
                shutil.copy2(GROWTH_STATE_PATH, os.path.join(backup_dir, backup_name))
        except OSError:
            pass

        try:
            os.makedirs(os.path.dirname(GROWTH_STATE_PATH), exist_ok=True)
            tmp = GROWTH_STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, GROWTH_STATE_PATH)
        except OSError as e:
            logger.warning(f"Failed to save growth state: {e}")

    @staticmethod
    def _evaluate_experiments(growth_state, roi_data):
        """评估历史实验表现

        通过 ROI 数据反推各策略组合的实际效果。
        """
        history = growth_state.get("experiment_history", {})
        if not history:
            return {"total_evaluated": 0, "improved": 0, "declined": 0, "results": []}

        evaluated = []
        improved = 0
        declined = 0

        # 从 roi_data 提取各来源 ROI 作为实验效果的近似反馈
        source_rois = {}
        if roi_data:
            for src, data in roi_data.get("by_source", {}).items():
                source_rois[src] = {
                    "roi": data.get("roi", 0),
                    "revenue": data.get("revenue", 0),
                }

        for key, exp_data in history.items():
            prev_roi = exp_data.get("avg_roi", 0)
            samples = exp_data.get("samples", 0)

            # 尝试匹配当前 ROI 数据
            parts = key.split("|")
            current_roi = prev_roi
            if len(parts) > 0:
                mkt = parts[0]
                if mkt in source_rois:
                    current_roi = source_rois[mkt]["roi"]

            change = current_roi - prev_roi
            if change > 0.1:
                improved += 1
            elif change < -0.1:
                declined += 1

            evaluated.append({
                "strategy_key": key,
                "previous_roi": round(prev_roi, 2),
                "current_roi": round(current_roi, 2),
                "change": round(change, 2),
                "samples": samples,
            })

        return {
            "total_evaluated": len(evaluated),
            "improved": improved,
            "declined": declined,
            "results": evaluated,
        }

    @staticmethod
    def _update_bandit_weights(growth_state, evaluation, roi_data):
        """更新 Bandit 权重"""
        weights = growth_state.get("bandit_weights", {})
        history = growth_state.get("experiment_history", {})

        # 对每个已评估的实验更新权重
        for result in evaluation.get("results", []):
            key = result["strategy_key"]
            current_roi = result["current_roi"]

            # 衰减旧权重
            old_weight = weights.get(key, 0.1)
            new_weight = old_weight * BANDIT_WEIGHT_DECAY

            # ROI 增益调整
            if current_roi > 2.0:
                new_weight += 0.05
            elif current_roi > 1.0:
                new_weight += 0.02
            elif current_roi < 0.5:
                new_weight -= 0.02

            weights[key] = round(max(new_weight, 0.01), 3)

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 3) for k, v in weights.items()}

        growth_state["bandit_weights"] = weights

        return {
            "total_strategies": len(weights),
            "top_strategy": max(weights, key=weights.get) if weights else None,
            "top_weight": max(weights.values()) if weights else 0,
        }

    @staticmethod
    def _prune_stale_experiments(growth_state):
        """淘汰超过时效的低效实验"""
        history = growth_state.get("experiment_history", {})
        weights = growth_state.get("bandit_weights", {})
        archived = growth_state.get("archived_experiments", [])
        removed = []

        for key, exp_data in list(history.items()):
            last_updated = exp_data.get("last_updated")
            if last_updated:
                try:
                    updated = _parse_dt(last_updated)
                    if updated is None:
                        continue
                    age = (datetime.now() - updated).days
                    if age > EXPERIMENT_PRUNE_AGE_DAYS:
                        weight = weights.get(key, 0)
                        if weight < 0.05:  # 低权重 + 超期 = 淘汰
                            exp_data["archived_at"] = datetime.now().isoformat()
                            archived.append(exp_data)
                            del history[key]
                            weights.pop(key, None)
                            removed.append(key)
                except (ValueError, TypeError):
                    continue

        growth_state["archived_experiments"] = archived
        growth_state["experiment_history"] = history
        growth_state["bandit_weights"] = weights

        return {"removed": len(removed), "archived_keys": removed}

    @staticmethod
    def _update_state(growth_state, evaluation, bandit_update,
                       new_experiments, pruned, cycle_number, dry_run):
        """整合所有变化到状态中"""
        changes = {
            "cycle_incremented": True,
            "experiments_evaluated": evaluation["total_evaluated"],
            "weights_updated": bandit_update["total_strategies"],
            "new_experiments_added": new_experiments["summary"]["experiments_generated"],
            "stale_pruned": pruned["removed"],
        }

        if dry_run:
            changes["saved"] = False
            changes["note"] = "dry run — state not persisted"
            return changes

        # 将新实验注入历史（占位）
        for exp in new_experiments.get("experiments", []):
            key = f"{exp['market']}|{exp['product']}|{exp['angle_id']}|{exp['pricing_tier']}"
            if key not in growth_state["experiment_history"]:
                growth_state["experiment_history"][key] = {
                    "created_at": datetime.now().isoformat(),
                    "samples": 0,
                    "avg_roi": 0,
                    "status": "active",
                }

        growth_state["cycle_number"] = cycle_number
        growth_state["last_cycle_at"] = datetime.now().isoformat()

        return changes

    @staticmethod
    def _generate_expansion_signals(growth_state, roi_data):
        """生成市场扩张信号"""
        weights = growth_state.get("bandit_weights", {})
        signals = []

        for key, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]:
            parts = key.split("|")
            if len(parts) >= 1:
                signals.append({
                    "market": parts[0],
                    "strategy_key": key,
                    "bandit_weight": weight,
                    "signal": "consider_expansion" if weight > 0.2 else "monitor",
                })

        return signals

    @staticmethod
    def get_growth_state():
        """直接加载当前增长状态"""
        return SelfLearningLoop._load_state()

    @staticmethod
    def get_experiment_history(limit=20):
        """获取实验历史摘要"""
        state = SelfLearningLoop._load_state()
        history = state.get("experiment_history", {})

        sorted_hist = sorted(
            history.items(),
            key=lambda x: x[1].get("created_at", ""),
            reverse=True,
        )

        return [
            {
                "strategy_key": key,
                "samples": data.get("samples", 0),
                "avg_roi": data.get("avg_roi", 0),
                "status": data.get("status", "unknown"),
                "created_at": data.get("created_at", ""),
            }
            for key, data in sorted_hist[:limit]
        ]
