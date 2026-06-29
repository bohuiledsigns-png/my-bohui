"""Agent Router — 客户→Agent分配路由

根据客户特征（国家、行业、状态、优先级）决定最佳Agent分配。
与WinnerSelector联动：优先选择历史胜率高的Agent。
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)


class AgentRouter:
    """Agent路由 — 客户特征→最佳Agent分配"""

    # 行业→推荐Agent映射
    INDUSTRY_AGENT_MAP = {
        "hotel": "consultant_agent",
        "restaurant": "hunter_agent",
        "retail": "closer_agent",
        "real estate": "closer_agent",
        "construction": "technical_agent",
        "manufacturing": "technical_agent",
        "healthcare": "consultant_agent",
        "education": "soft_seller_agent",
        "entertainment": "hunter_agent",
    }

    # 国家→推荐Agent映射
    COUNTRY_AGENT_MAP = {
        "US": "hunter_agent",
        "CA": "hunter_agent",
        "DE": "technical_agent",
        "UK": "consultant_agent",
        "FR": "consultant_agent",
        "AE": "closer_agent",
        "SA": "closer_agent",
        "JP": "consultant_agent",
        "AU": "hunter_agent",
        "SG": "consultant_agent",
    }

    @staticmethod
    def route(customer_data: dict) -> dict:
        """为给定客户数据推荐最佳Agent

        Args:
            customer_data: {
                country, industry, state, priority_class,
                message_count, conversion_score, ...
            }

        Returns:
            dict: {
                recommended_agent_id, recommended_agent_name,
                alternatives: [...],
                reason: str,
            }
        """
        country = (customer_data.get("country") or "").upper()
        industry = (customer_data.get("industry") or "").lower()
        state = (customer_data.get("state") or "NEW").upper()
        priority = (customer_data.get("priority_class") or "C").upper()

        # 1. 按行业推荐
        recommended = None
        reason = ""

        for key, agent_id in AgentRouter.INDUSTRY_AGENT_MAP.items():
            if key in industry:
                recommended = agent_id
                reason = f"Industry '{industry}' matched to {agent_id}"
                break

        # 2. 按国家推荐（覆盖行业）
        if country in AgentRouter.COUNTRY_AGENT_MAP:
            country_agent = AgentRouter.COUNTRY_AGENT_MAP[country]
            if not recommended:
                recommended = country_agent
                reason = f"Country '{country}' matched to {country_agent}"
            elif country_agent != recommended:
                # 国家推荐有更高优先级
                recommended = country_agent
                reason = f"Country '{country}' overrides industry match → {country_agent}"

        # 3. 按状态推荐
        if not recommended:
            if state == "NEW":
                recommended = "consultant_agent"
                reason = "New lead → consultant for initial qualification"
            elif state in ("BUDGET", "OBJECTION"):
                recommended = "hunter_agent"
                reason = "Budget/objection → hunter for aggressive pricing"
            elif state == "FINAL":
                recommended = "closer_agent"
                reason = "Final stage → closer for deal closing"
            else:
                recommended = "consultant_agent"
                reason = "Default to consultant for general inquiries"

        # 4. 按优先级微调
        if priority == "A" and recommended not in ("closer_agent", "hunter_agent"):
            alternatives = list(AgentRouter.get_alternatives(recommended))
            if "closer_agent" in alternatives:
                recommended = "closer_agent"
                reason += " | A-priority upgraded to closer_agent"

        # 获取Agent名称
        agent_names = {
            "hunter_agent": "Hunter (Alex)",
            "consultant_agent": "Consultant (Sarah)",
            "soft_seller_agent": "Soft Seller (Emma)",
            "technical_agent": "Technical (Mike)",
            "closer_agent": "Closer (Diana)",
        }

        return {
            "recommended_agent_id": recommended,
            "recommended_agent_name": agent_names.get(recommended, recommended),
            "reason": reason,
            "alternatives": AgentRouter.get_alternatives(recommended),
            "matched_on": {
                "country": country,
                "industry": industry,
                "state": state,
                "priority": priority,
            },
        }

    @staticmethod
    def get_alternatives(agent_id: str) -> list:
        """获取指定Agent的替代方案"""
        alternatives_map = {
            "hunter_agent": ["closer_agent", "consultant_agent"],
            "consultant_agent": ["technical_agent", "soft_seller_agent"],
            "soft_seller_agent": ["consultant_agent", "hunter_agent"],
            "technical_agent": ["consultant_agent", "closer_agent"],
            "closer_agent": ["hunter_agent", "consultant_agent"],
        }
        return alternatives_map.get(agent_id, ["consultant_agent"])


# 快捷入口
router = AgentRouter()


def route_customer(customer_data: dict) -> dict:
    return AgentRouter.route(customer_data)
