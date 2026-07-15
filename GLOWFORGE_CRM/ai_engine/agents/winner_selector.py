"""Winner Selector — 优胜选择器 + 学习进化系统

核心功能：
  1. 记录每个Agent的胜率
  2. 记录每个Agent在特定场景的胜率
  3. 低胜率Agent从高胜率Agent学习
  4. 根据场景动态调整Agent选择权重
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from database import get_db


class WinnerSelector:
    """优胜选择器 — 记录学习 + 权重调整"""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        """确保数据库表存在（由主database.py的init负责，此处做兜底）"""
        pass

    def record_result(self, competition_id: int, winner_agent_id: str,
                      all_scores: list, context: dict = None) -> bool:
        """记录竞争结果，更新Agent权重

        Args:
            competition_id: 竞争ID
            winner_agent_id: 获胜Agent ID
            all_scores: 所有Agent的得分 [{agent_id, overall, scores}]
            context: {state, priority, country, ...}

        Returns:
            bool: 是否成功
        """
        try:
            conn = get_db()

            # 更新每个Agent的胜率统计
            for score_data in all_scores:
                agent_id = score_data["agent_id"]
                is_winner = 1 if agent_id == winner_agent_id else 0
                overall = score_data["overall"]

                # 查找或创建Agent权重记录
                existing = conn.execute(
                    "SELECT id FROM v5_agent_weights WHERE agent_id=?",
                    (agent_id,)
                ).fetchone()

                if existing:
                    # 更新
                    conn.execute(
                        """UPDATE v5_agent_weights SET
                           total_matches = total_matches + 1,
                           wins = wins + ?,
                           last_score = ?,
                           last_win = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_win END,
                           updated_at = CURRENT_TIMESTAMP
                           WHERE agent_id=?""",
                        (is_winner, overall, is_winner, agent_id)
                    )
                else:
                    # 创建
                    conn.execute(
                        """INSERT INTO v5_agent_weights
                           (agent_id, total_matches, wins, last_score, win_rate)
                           VALUES (?, 1, ?, ?, ?)""",
                        (agent_id, is_winner, overall, overall if is_winner else 0)
                    )

                # 记录场景胜率
                state = (context or {}).get("state", "UNKNOWN")
                prio = (context or {}).get("priority", "C")

                scene_existing = conn.execute(
                    "SELECT id FROM v5_agent_weights "
                    "WHERE agent_id=? AND scene_state=? AND scene_priority=?",
                    (agent_id, state, prio)
                ).fetchone()

                if scene_existing:
                    conn.execute(
                        """UPDATE v5_agent_weights SET
                           total_matches = total_matches + 1,
                           wins = wins + ?,
                           updated_at = CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (is_winner, scene_existing["id"])
                    )
                else:
                    conn.execute(
                        """INSERT INTO v5_agent_weights
                           (agent_id, scene_state, scene_priority,
                            total_matches, wins, win_rate)
                           VALUES (?,?,?, 1, ?, ?)""",
                        (agent_id, state, prio, is_winner, overall if is_winner else 0)
                    )

            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def get_agent_weights(self, scene_state: str = "", scene_priority: str = "") -> list:
        """获取Agent权重

        Args:
            scene_state: 可选，过滤场景状态
            scene_priority: 可选，过滤场景优先级

        Returns:
            list: [{agent_id, weight, win_rate, total_matches, ...}]
        """
        try:
            conn = get_db()
            if scene_state and scene_priority:
                rows = conn.execute(
                    """SELECT agent_id, SUM(wins) as total_wins,
                              SUM(total_matches) as total_matches,
                              CASE WHEN SUM(total_matches) > 0
                                   THEN ROUND(CAST(SUM(wins) AS FLOAT) / SUM(total_matches) * 100, 1)
                                   ELSE 0 END as win_rate
                       FROM v5_agent_weights
                       WHERE scene_state=? AND scene_priority=?
                       GROUP BY agent_id
                       ORDER BY win_rate DESC""",
                    (scene_state, scene_priority)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT agent_id, SUM(wins) as total_wins,
                              SUM(total_matches) as total_matches,
                              CASE WHEN SUM(total_matches) > 0
                                   THEN ROUND(CAST(SUM(wins) AS FLOAT) / SUM(total_matches) * 100, 1)
                                   ELSE 0 END as win_rate,
                              AVG(last_score) as avg_score
                       FROM v5_agent_weights
                       WHERE scene_state IS NULL AND scene_priority IS NULL
                       GROUP BY agent_id
                       ORDER BY win_rate DESC"""
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_best_agent_for_scene(self, state: str, priority: str) -> dict:
        """获取特定场景的最佳Agent

        Args:
            state: 客户状态
            priority: 优先级 A/B/C

        Returns:
            dict: {agent_id, win_rate, total_matches}
        """
        weights = self.get_agent_weights(state, priority)
        if weights:
            best = weights[0]
            return {
                "agent_id": best["agent_id"],
                "win_rate": best["win_rate"],
                "total_matches": best["total_matches"],
            }
        return {}

    def get_learning_suggestions(self, min_matches: int = 5) -> list:
        """为低胜率Agent提供学习建议

        分析哪些Agent在哪些场景表现差，
        建议他们从同场景的高胜率Agent学习。

        Returns:
            list: [{agent_id, weakness_scene, win_rate, suggested_mentor, mentor_win_rate}]
        """
        try:
            conn = get_db()
            rows = conn.execute(
                """SELECT agent_id, scene_state, scene_priority,
                          wins, total_matches,
                          CASE WHEN total_matches > 0
                               THEN ROUND(CAST(wins AS FLOAT) / total_matches * 100, 1)
                               ELSE 0 END as win_rate
                   FROM v5_agent_weights
                   WHERE scene_state IS NOT NULL
                     AND total_matches >= ?
                   ORDER BY win_rate ASC""",
                (min_matches,)
            ).fetchall()
            conn.close()

            suggestions = []
            for r in rows:
                if r["win_rate"] < 40:  # 胜率低于40%需要学习
                    # 找该场景的优胜者
                    mentor = self.get_best_agent_for_scene(
                        r["scene_state"], r["scene_priority"]
                    )
                    if mentor and mentor.get("agent_id") != r["agent_id"]:
                        suggestions.append({
                            "agent_id": r["agent_id"],
                            "weakness_scene": f"{r['scene_state']}/{r['scene_priority']}",
                            "win_rate": r["win_rate"],
                            "total_matches": r["total_matches"],
                            "suggested_mentor": mentor.get("agent_id", ""),
                            "mentor_win_rate": mentor.get("win_rate", 0),
                        })
            return suggestions
        except Exception:
            return []

    def get_adjusted_weights(self, state: str = "", priority: str = "C") -> dict:
        """获取调整后的Agent权重（用于Agent选择）

        结合基础权重和场景学习数据。

        Returns:
            dict: {agent_id: adjusted_weight}
        """
        # 基础权重
        base_weights = {
            "hunter_agent": 1.0,
            "consultant_agent": 1.0,
            "soft_seller_agent": 0.8,
            "technical_agent": 0.7,
            "closer_agent": 1.0,
        }

        # 从数据库获取学习数据调整
        if state:
            scene_weights = self.get_agent_weights(state, priority)
            for sw in scene_weights:
                aid = sw["agent_id"]
                if aid in base_weights and sw["total_matches"] >= 3:
                    # 根据胜率调整权重 (±30%)
                    wr = sw["win_rate"] / 100.0
                    adjustment = 0.7 + (wr * 0.6)  # 0.7~1.3 range
                    base_weights[aid] = round(base_weights.get(aid, 1.0) * adjustment, 2)

        return base_weights

    def get_agent_evolution_report(self) -> dict:
        """生成Agent进化报告

        Returns:
            dict: {
                overall_stats: {...},
                best_agents: [...],
                learning_suggestions: [...],
                scene_performance: {...},
            }
        """
        all_weights = self.get_agent_weights()
        suggestions = self.get_learning_suggestions()

        # 总体统计
        total_matches = sum(w.get("total_matches", 0) for w in all_weights)
        avg_win_rate = (
            sum(w.get("win_rate", 0) for w in all_weights) / len(all_weights)
            if all_weights else 0
        )

        return {
            "total_competitions": total_matches,
            "average_win_rate": round(avg_win_rate, 1),
            "active_agents": len(all_weights),
            "best_agents": all_weights[:3] if all_weights else [],
            "learning_suggestions": suggestions,
        }


# 快捷入口
selector = WinnerSelector()


def record_competition_result(competition_id: int, winner_agent_id: str,
                               all_scores: list, context: dict = None) -> bool:
    return selector.record_result(competition_id, winner_agent_id, all_scores, context)


def get_best_agent(state: str, priority: str) -> dict:
    return selector.get_best_agent_for_scene(state, priority)


def get_evolution_report() -> dict:
    return selector.get_agent_evolution_report()
