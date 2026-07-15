"""Agent Competition — 并行竞争评分系统（核心）

同一客户消息 → 多个Agent并行生成回复 → 评分选出最优

评分维度：
  - relevance: 与客户消息的相关度 (0-100)
  - persuasiveness: 说服力 (0-100)
  - conversion_intent: 转化意图强度 (0-100)
  - context_consistency: 与上下文的一致性 (0-100)
  - overall: 综合得分（加权平均）
"""

import sys
import os
import json
import random
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from database import get_db

# 评分权重
SCORE_WEIGHTS = {
    "relevance": 0.30,
    "persuasiveness": 0.25,
    "conversion_intent": 0.25,
    "context_consistency": 0.20,
}


class AgentCompetition:
    """Agent竞争评分系统"""

    def __init__(self):
        self.agents = {}
        self._load_agents()

    def _load_agents(self):
        """加载所有Agent"""
        try:
            from .hunter_agent import HunterAgent
            from .consultant_agent import ConsultantAgent
            from .soft_seller_agent import SoftSellerAgent
            from .technical_agent import TechnicalAgent
            from .closer_agent import CloserAgent

            self.agents = {
                "hunter_agent": HunterAgent,
                "consultant_agent": ConsultantAgent,
                "soft_seller_agent": SoftSellerAgent,
                "technical_agent": TechnicalAgent,
                "closer_agent": CloserAgent,
            }
        except ImportError:
            pass

    def get_agent_ids(self) -> list:
        """获取所有Agent ID列表"""
        return list(self.agents.keys())

    def get_active_agents(self, customer_state: str = "", priority_class: str = "C",
                          customer_msg: str = "") -> list:
        """根据场景选择应该参与竞争的Agent子集

        Args:
            customer_state: NEW / BUDGET / OBJECTION / FINAL
            priority_class: A / B / C
            customer_msg: 客户消息

        Returns:
            list: [agent_id, ...]
        """
        state = customer_state.upper()

        # 所有Agent默认参与
        all_agents = self.get_agent_ids()

        # 根据场景筛选
        if state == "NEW":
            # 初次接触：Consultant + Soft Seller + Hunter
            return ["consultant_agent", "soft_seller_agent", "hunter_agent"]
        elif state in ("BUDGET", "OBJECTION"):
            # 预算/异议：Hunter + Consultant + Closer
            return ["hunter_agent", "consultant_agent", "closer_agent"]
        elif state == "FINAL":
            # 成交阶段：Closer + Hunter
            return ["closer_agent", "hunter_agent"]
        elif state in ("WON", "DELIVERED"):
            # 售后：Soft Seller + Consultant
            return ["soft_seller_agent", "consultant_agent"]

        # 按优先级
        if priority_class == "A":
            return ["closer_agent", "hunter_agent", "consultant_agent"]
        elif priority_class == "B":
            return ["consultant_agent", "technical_agent", "soft_seller_agent"]
        else:
            return ["hunter_agent", "soft_seller_agent"]

    def generate_all_replies(self, customer_msg: str, context: dict = None,
                             agent_ids: list = None) -> dict:
        """让多个Agent生成回复（返回每个Agent的指令注入）

        Args:
            customer_msg: 客户消息
            context: {base_price, region_multiplier, ...}
            agent_ids: 参与竞争的Agent列表，None=全部

        Returns:
            dict: {agent_id: agent_instruction, ...}
        """
        if agent_ids is None:
            agent_ids = self.get_agent_ids()

        replies = {}
        for agent_id in agent_ids:
            agent_class = self.agents.get(agent_id)
            if agent_class:
                try:
                    instruction = agent_class.generate_reply(customer_msg, context)
                    replies[agent_id] = {
                        "agent_name": getattr(agent_class, "NAME", agent_id),
                        "strategy": getattr(agent_class, "STRATEGY", ""),
                        "pricing_mode": getattr(agent_class, "PRICING_MODE", ""),
                        "instruction": instruction,
                    }
                except Exception as e:
                    replies[agent_id] = {
                        "agent_name": agent_id,
                        "error": str(e),
                    }
        return replies

    def score_reply(self, agent_id: str, reply_text: str, customer_msg: str,
                    context: dict = None) -> dict:
        """对单条回复进行评分

        注意：在实际应用中，评分应由LLM进行。
        此处使用基于规则的近似评分作为演示。

        Args:
            agent_id: Agent ID
            reply_text: 回复内容
            customer_msg: 客户消息
            context: 上下文

        Returns:
            dict: {scores: {...}, overall: float}
        """
        scores = {}

        # Relevance: 基于回复与客户消息的文本重叠
        msg_words = set(customer_msg.lower().split())
        reply_words = set(reply_text.lower().split())
        if msg_words:
            overlap = len(msg_words & reply_words) / len(msg_words)
            scores["relevance"] = round(min(overlap * 100, 100), 1)
        else:
            scores["relevance"] = 50.0

        # Persuasiveness: 基于说服性关键词
        persuasive_words = {"guarantee", "proven", "result", "save", "investment",
                           "value", "quality", "best", "expert", "trust", "reliable"}
        persuasive_count = sum(1 for w in persuasive_words if w in reply_text.lower())
        scores["persuasiveness"] = round(min(persuasive_count * 10, 100), 1)

        # Conversion Intent: 基于成交关键词
        conversion_words = {"order", "today", "now", "limited", "discount",
                           "special", "offer", "deadline", "ready", "invoice",
                           "decision", "quote", "ship"}
        conversion_count = sum(1 for w in conversion_words if w in reply_text.lower())
        scores["conversion_intent"] = round(min(conversion_count * 8, 100), 1)

        # Context Consistency: 基于agent_id的特征匹配
        if agent_id == "hunter_agent":
            urgency_words = {"urgent", "limited", "today", "now", "fast", "immediate"}
            consistency = sum(1 for w in urgency_words if w in reply_text.lower())
            scores["context_consistency"] = round(min(consistency * 12 + 40, 100), 1)
        elif agent_id == "consultant_agent":
            consult_words = {"recommend", "suggest", "option", "need", "solution", "fit"}
            consistency = sum(1 for w in consult_words if w in reply_text.lower())
            scores["context_consistency"] = round(min(consistency * 12 + 40, 100), 1)
        elif agent_id == "technical_agent":
            tech_words = {"spec", "material", "mm", "led", "certification", "quality"}
            consistency = sum(1 for w in tech_words if w in reply_text.lower())
            scores["context_consistency"] = round(min(consistency * 12 + 40, 100), 1)
        elif agent_id == "closer_agent":
            close_words = {"now", "today", "offer", "limited", "decision", "invoice", "ready"}
            consistency = sum(1 for w in close_words if w in reply_text.lower())
            scores["context_consistency"] = round(min(consistency * 12 + 40, 100), 1)
        else:
            scores["context_consistency"] = 60.0

        # 计算加权总分
        overall = sum(
            scores.get(dim, 0) * weight
            for dim, weight in SCORE_WEIGHTS.items()
        )
        overall = round(overall, 1)

        return {
            "agent_id": agent_id,
            "scores": scores,
            "overall": overall,
        }

    def run_competition(self, customer_msg: str, context: dict = None,
                        agent_ids: list = None) -> dict:
        """运行一轮Agent竞争

        Args:
            customer_msg: 客户消息
            context: 上下文
            agent_ids: 参与竞争的Agent列表

        Returns:
            dict: {
                winner_agent_id, winner_name,
                all_scores: [{agent_id, scores, overall}],
                replies: {agent_id: instruction},
                competition_id,
            }
        """
        if agent_ids is None:
            agent_ids = self.get_active_agents(
                customer_state=(context or {}).get("state", ""),
                priority_class=(context or {}).get("priority", "C"),
            )

        # 1. 所有Agent生成回复
        replies = self.generate_all_replies(customer_msg, context, agent_ids)

        # 2. 评分
        scored = []
        for agent_id in agent_ids:
            reply_data = replies.get(agent_id, {})
            instruction = reply_data.get("instruction", "")
            score_result = self.score_reply(
                agent_id, instruction, customer_msg, context
            )
            scored.append(score_result)

        # 3. 找出优胜者
        scored.sort(key=lambda x: x["overall"], reverse=True)
        winner = scored[0] if scored else None

        # 4. 记录到数据库
        competition_id = self._log_competition(
            customer_msg, agent_ids, scored, winner, context
        )

        return {
            "winner_agent_id": winner["agent_id"] if winner else None,
            "winner_name": replies.get(winner["agent_id"], {}).get("agent_name", "") if winner else "",
            "winner_score": winner["overall"] if winner else 0,
            "all_scores": scored,
            "replies": replies,
            "competition_id": competition_id,
            "agent_count": len(agent_ids),
        }

    def _log_competition(self, customer_msg: str, agent_ids: list,
                         scored: list, winner: dict, context: dict = None) -> int:
        """记录竞争结果到数据库"""
        try:
            conn = get_db()
            if winner:
                winner_agent = winner["agent_id"]
                winner_score = winner["overall"]
            else:
                winner_agent = ""
                winner_score = 0

            scores_json = json.dumps([
                {"agent_id": s["agent_id"], "overall": s["overall"], "scores": s["scores"]}
                for s in scored
            ], ensure_ascii=False)

            cur = conn.execute(
                """INSERT INTO v5_competition_log
                   (customer_msg_snippet, agent_ids, scores_json,
                    winner_agent_id, winner_score, customer_state, context_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    customer_msg[:200],
                    ",".join(agent_ids),
                    scores_json,
                    winner_agent,
                    winner_score,
                    (context or {}).get("state", ""),
                    json.dumps(context or {}, ensure_ascii=False),
                )
            )
            competition_id = cur.lastrowid
            conn.commit()
            conn.close()
            return competition_id
        except Exception:
            return 0


# 快捷入口
competition = AgentCompetition()


def run_competition(customer_msg: str, context: dict = None, agent_ids: list = None) -> dict:
    return competition.run_competition(customer_msg, context, agent_ids)


def get_active_agents(customer_state: str = "", priority_class: str = "C") -> list:
    return competition.get_active_agents(customer_state, priority_class)
