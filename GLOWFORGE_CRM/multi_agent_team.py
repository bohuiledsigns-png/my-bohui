"""Multi-Agent Sales Team — 多Agent销售团队（V5）

管理按区域/语言/文化定制的AI销售代表，
为每个线索选择最合适的Agent执行触达。
"""

import os
import sys
import json
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 默认Agent配置
DEFAULT_AGENTS = [
    {
        "agent_id": "NA_Sales",
        "name": "James (North America)",
        "region": "NA",
        "languages": ["en"],
        "pricing_multiplier": 1.0,
        "culture_context": (
            "North American business culture: direct, value-driven, "
            "emphasize quality, warranty, and delivery speed. "
            "Use imperial units (inches/feet). "
            "Quote in USD. Reference北美 case studies."
        ),
    },
    {
        "agent_id": "EU_Sales",
        "name": "Elena (Europe)",
        "region": "EU",
        "languages": ["en", "de", "fr"],
        "pricing_multiplier": 0.95,
        "culture_context": (
            "European business culture: formal, detail-oriented, "
            "emphasize certifications (CE, RoHS), compliance, and sustainability. "
            "Use metric units (cm/m). Quote in EUR or local currency. "
            "Reference European case studies. Be prepared for technical specifications."
        ),
    },
    {
        "agent_id": "APAC_Sales",
        "name": "Yuki (Asia Pacific)",
        "region": "APAC",
        "languages": ["en", "ja", "zh", "ko"],
        "pricing_multiplier": 1.05,
        "culture_context": (
            "Asia Pacific business culture: relationship-first, respectful, "
            "emphasize value for money, reliability, and after-sales service. "
            "Use metric units. Quote in USD or local currency. "
            "Be patient with decision-making process. Reference APAC case studies."
        ),
    },
]


class MultiAgentTeam:
    """多Agent销售团队管理"""

    def __init__(self):
        self.default_agents = DEFAULT_AGENTS

    def get_all_agents(self) -> list:
        """获取所有Agent配置（数据库 + 默认）

        Returns:
            list: [{agent_id, name, region, languages, pricing_multiplier, ...}]
        """
        results = []
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT ap.*, r.code as region_code, r.name as region_name
                   FROM agent_profiles ap
                   LEFT JOIN regions r ON ap.region_id = r.id
                   ORDER BY ap.agent_id"""
            ).fetchall()
            conn.close()
            for r in rows:
                results.append({
                    "agent_id": r["agent_id"],
                    "name": r.get("display_name") or r["agent_id"],
                    "region": r["region_code"] or "",
                    "region_name": r["region_name"] or "",
                    "languages": json.loads(r["languages"]) if isinstance(r["languages"], str) else (r["languages"] or []),
                    "pricing_multiplier": r["pricing_multiplier"],
                    "culture_context": r.get("culture_context", ""),
                })
        except Exception:
            pass

        # 回退到默认
        if not results:
            for agent in self.default_agents:
                results.append({
                    "agent_id": agent["agent_id"],
                    "name": agent["name"],
                    "region": agent["region"],
                    "languages": agent["languages"],
                    "pricing_multiplier": agent["pricing_multiplier"],
                    "culture_context": agent["culture_context"],
                })

        return results

    def select_agent(self, country: str, language: str = "English") -> dict:
        """为特定国家/语言选择最合适的Agent

        Args:
            country: 国家代码（US, DE, JP...）
            language: 客户语言

        Returns:
            dict: {agent_id, name, region, pricing_multiplier, culture_context, language}
        """
        # 确定区域
        try:
            from region_engine import RegionEngine
            region_info = RegionEngine().get_region_for_country(country)
            region_code = region_info["code"]
        except Exception:
            region_code = "APAC"

        # 区域到Agent的映射
        region_agent_map = {
            "NA": "NA_Sales",
            "EU": "EU_Sales",
            "APAC": "APAC_Sales",
            "LATAM": "NA_Sales",
            "MEA": "EU_Sales",
        }
        target_agent_id = region_agent_map.get(region_code, "APAC_Sales")

        # 查找Agent
        all_agents = self.get_all_agents()
        for agent in all_agents:
            if agent["agent_id"] == target_agent_id:
                return {
                    "agent_id": agent["agent_id"],
                    "name": agent["name"],
                    "region": agent.get("region", region_code),
                    "pricing_multiplier": agent.get("pricing_multiplier", 1.0),
                    "culture_context": agent.get("culture_context", ""),
                    "language": language,
                }

        # 兜底
        return {
            "agent_id": "APAC_Sales",
            "name": "Yuki (Asia Pacific)",
            "region": "APAC",
            "pricing_multiplier": 1.05,
            "culture_context": DEFAULT_AGENTS[2]["culture_context"],
            "language": language,
        }

    def build_agent_context(self, agent_id: str, customer_data: dict) -> str:
        """构建Agent上下文提示（供AI引擎使用）

        Args:
            agent_id: Agent ID
            customer_data: {name, company, country, industry, ...}

        Returns:
            str: 格式化的上下文文本
        """
        agents = self.get_all_agents()
        agent = None
        for a in agents:
            if a["agent_id"] == agent_id:
                agent = a
                break

        if not agent:
            agent = {
                "agent_id": agent_id,
                "name": agent_id,
                "region": "APAC",
                "pricing_multiplier": 1.0,
                "culture_context": "Standard sales approach.",
                "languages": ["en"],
            }

        name = customer_data.get("name", "the customer")
        company = customer_data.get("company", "")
        industry = customer_data.get("industry", "business")
        country = customer_data.get("country", "")
        country_name = self._country_code_to_name(country)

        ctx = f"""You are {agent['name']}, a sales representative for Bohui GLOWFORGE.
Region: {agent.get('region', 'Global')}
Target customer: {name} from {company or country_name or country}
Industry: {industry}

Pricing note: Apply a {agent.get('pricing_multiplier', 1.0)}x multiplier to base prices.

Cultural context:
{agent.get('culture_context', 'Standard approach.')}

Communication style:
- Always be professional and helpful
- Focus on value proposition for {industry} businesses
- Adapt formality level to the customer's communication style
- When discussing prices, quote in the appropriate currency for the region
- Reference relevant case studies from the same region when possible
"""
        return ctx

    def get_agent_stats(self, days: int = 30) -> list:
        """获取各Agent触达统计

        Returns:
            list: [{agent_id, total_leads, contacted, converted, conversion_rate}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT assigned_agent, COUNT(*) as total,
                          SUM(CASE WHEN lead_status IN ('contacted','qualified','negotiating','hot','customer') THEN 1 ELSE 0 END) as contacted,
                          SUM(CASE WHEN lead_status='customer' THEN 1 ELSE 0 END) as converted
                   FROM customers
                   WHERE assigned_agent IS NOT NULL AND assigned_agent != ''
                   GROUP BY assigned_agent"""
            ).fetchall()
            conn.close()

            agents_map = {}
            for r in rows:
                agent_id = r["assigned_agent"]
                total = r["total"]
                contacted = r["contacted"]
                converted = r["converted"]
                agents_map[agent_id] = {
                    "agent_id": agent_id,
                    "total_leads": total,
                    "contacted": contacted,
                    "converted": converted,
                    "conversion_rate": round(converted / contacted * 100, 1) if contacted > 0 else 0,
                }

            return list(agents_map.values())
        except Exception:
            return []

    def _country_code_to_name(self, code: str) -> str:
        """ISO国家代码转名称"""
        names = {
            "US": "United States", "CA": "Canada",
            "GB": "United Kingdom", "DE": "Germany", "FR": "France",
            "IT": "Italy", "ES": "Spain", "NL": "Netherlands",
            "JP": "Japan", "AU": "Australia", "SG": "Singapore",
            "BR": "Brazil", "MX": "Mexico",
            "AE": "UAE", "SA": "Saudi Arabia", "ZA": "South Africa",
        }
        return names.get(code.upper(), code)


# ==================== 测试 ====================
if __name__ == "__main__":
    team = MultiAgentTeam()

    print("=== All Agents ===")
    for a in team.get_all_agents():
        print(f"  {a['agent_id']}: {a.get('name', '?')} ({a.get('region', '?')}) "
              f"multiplier={a.get('pricing_multiplier', '?')}")

    print("\n=== Agent Selection ===")
    for country in ["US", "DE", "JP", "BR", "AE"]:
        agent = team.select_agent(country)
        print(f"  {country} → {agent['agent_id']} ({agent['name']})")

    print("\n=== Agent Context ===")
    ctx = team.build_agent_context("EU_Sales", {
        "name": "Hans Mueller",
        "company": "Bavarian Hotels GmbH",
        "country": "DE",
        "industry": "hotel",
    })
    print(f"  {ctx[:300]}...")
