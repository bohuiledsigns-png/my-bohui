"""Global Lead Router — 全球线索路由引擎（V5）

区域感知的线索评分与路由：结合国家/地区市场潜力、
行业匹配度、渠道质量，将线索分派到最合适的区域销售团队。
"""

import os
import sys
import re
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# 区域市场潜力评分（满分10）
REGION_POTENTIAL = {
    "NA": 10,  # 北美：高客单价、成熟市场
    "EU": 8,   # 欧洲：中高客单价
    "APAC": 6, # 亚太：中客单价、量大
    "LATAM": 4, # 拉美：中低客单价
    "MEA": 3,  # 中东非洲：低客单价但增长快
}

# 区域Agent映射（谁负责哪个区域的线索）
REGION_AGENTS = {
    "NA": "NA_Sales",
    "EU": "EU_Sales",
    "APAC": "APAC_Sales",
    "LATAM": "NA_Sales",    # 拉美由 NA 团队兼管
    "MEA": "EU_Sales",      # 中东非洲由 EU 团队兼管
}

# 国家市场潜力评分（基于 LED  signage 行业需求）
_COUNTRY_SCORES = {
    "US": 10, "CA": 8,
    "GB": 9, "DE": 9, "FR": 8, "IT": 7, "ES": 7, "NL": 8, "CH": 7,
    "JP": 8, "AU": 8, "SG": 8, "KR": 7, "NZ": 6, "HK": 7,
    "AE": 8, "SA": 7, "QA": 6, "ZA": 5,
    "BR": 5, "MX": 5, "AR": 4, "CL": 4, "CO": 4,
}

# 行业需求评分
_INDUSTRY_SCORES = {
    "restaurant": 10,  # 餐饮连锁 = 最高需求
    "hotel": 9,
    "retail": 8,
    "salon": 7,
    "office": 6,
    "warehouse": 4,
    "other": 3,
}

# 渠道质量评分
_SOURCE_SCORES = {
    "inquiry": 10,  # 主动询盘 = 最高意向
    "referral": 9,  # 推荐 = 高信任
    "whatsapp_inquiry": 10,
    "website_inquiry": 9,
    "import": 7,    # 数据导入 = 中等
    "scrape": 5,    # 抓取 = 低
    "manual": 6,    # 手动录入 = 中低
}

# 需求关键词检测 — 扩展版
_DEMAND_REGEX = [
    (r"\bled\b", 8),
    (r"\bsign\b", 5),
    (r"\bneon\b", 7),
    (r"\border\b", 8),
    (r"\bprice\b", 5),
    (r"\bquote\b", 7),
    (r"\bhow much\b", 6),
    (r"\bbanner\b", 4),
    (r"\billuminate\b", 8),
    (r"\bfront\b", 4),
    (r"\bfaçade\b", 7),
    (r"\bstorefront\b", 8),
    (r"\bshop\b", 4),
    (r"\brestaurant\b", 8),
    (r"\breopen\b", 9),
    (r"\bopen(ing|ed)\b", 5),
    (r"\brebrand\b", 9),
    (r"\brenovat\b", 7),
    (r"\bnew (store|shop|location)\b", 8),
    (r"\bfranchise\b", 9),
    (r"\bchain\b", 7),
    (r"\bexpansion\b", 7),
    (r"\b3d\b", 5),
    (r"\bcustom\b", 6),
    (r"\bwholesale\b", 6),
    (r"\bmanufactur\b", 5),
    (r"\bchina\b", 3),
    (r"\bshipping\b", 5),
]


class GlobalLeadRouter:
    """全球线索路由引擎"""

    def score_lead_global(self, customer_id: int,
                          customer_data: Optional[dict] = None) -> dict:
        """全球综合评分

        Args:
            customer_id: 客户ID
            customer_data: 预加载的客户数据（可选，避免重复查询）

        Returns:
            dict: {
                score: int (0-100),
                level: str (premium/standard/nurture),
                region: str (区域代码),
                agent: str (Agent ID),
                dimensions: {country, industry, source, demand, region_potential},
                reasons: [str]
            }
        """
        if customer_data is None:
            try:
                sys.path.insert(0, BASE_DIR)
                from database import get_db

                conn = get_db()
                conn.row_factory = None  # simple tuple
                row = conn.execute(
                    "SELECT name, company, country, source, notes, lead_score FROM customers WHERE id=?",
                    (customer_id,),
                ).fetchone()
                conn.close()
                if not row:
                    return {"error": f"Customer {customer_id} not found"}
                customer_data = {
                    "name": row[0] or "",
                    "company": row[1] or "",
                    "country": row[2] or "",
                    "source": row[3] or "",
                    "notes": row[4] or "",
                }
            except Exception as e:
                return {"error": str(e)}

        country = (customer_data.get("country") or "").upper().strip()
        company = customer_data.get("company") or ""
        notes = customer_data.get("notes") or ""
        source = customer_data.get("source") or ""
        name = customer_data.get("name") or ""

        dimensions = {}
        reasons = []

        # 1. 国家评分（0-25）
        country_score = _COUNTRY_SCORES.get(country, 0)
        country_weighted = round(country_score * 2.5, 1)
        dimensions["country"] = country_weighted
        if country_score > 0:
            reasons.append(f"Country {country}: {country_weighted}/25")
        else:
            reasons.append(f"Country {country}: unknown → 0/25")

        # 2. 区域市场潜力加成（0-10）
        try:
            from region_engine import RegionEngine
            region_info = RegionEngine().get_region_for_country(country)
            region_code = region_info["code"]
            region_bonus = REGION_POTENTIAL.get(region_code, 3)
        except Exception:
            region_code = "APAC"
            region_bonus = 3
        dimensions["region_potential"] = region_bonus
        reasons.append(f"Region {region_code}: +{region_bonus}/10")

        # 3. 行业评分（0-20）
        combo = f"{company} {notes}".lower()
        industry = self._detect_industry(combo)
        industry_score = _INDUSTRY_SCORES.get(industry, 3)
        industry_weighted = round(industry_score * 2.0, 1)
        dimensions["industry"] = industry_weighted
        reasons.append(f"Industry {industry}: {industry_weighted}/20")

        # 4. 渠道质量（0-20）
        source_score = _SOURCE_SCORES.get(source.lower(), 5)
        source_weighted = round(source_score * 2.0, 1)
        dimensions["source"] = source_weighted
        reasons.append(f"Source {source}: {source_weighted}/20")

        # 5. 需求关键词匹配（0-25）
        demand_score = 0
        matched_kws = []
        for pattern, weight in _DEMAND_REGEX:
            if re.search(pattern, combo, re.IGNORECASE):
                demand_score += weight
                matched_kws.append(pattern.strip("\\b"))
        demand_score = min(demand_score, 25)
        dimensions["demand"] = demand_score
        if matched_kws:
            reasons.append(f"Keywords [{','.join(matched_kws[:3])}]: +{demand_score}/25")
        else:
            reasons.append(f"No demand keywords: 0/25")

        # 总分
        total = round(country_weighted + region_bonus + industry_weighted
                      + source_weighted + demand_score, 1)

        # 等级
        if total >= 70:
            level = "premium"
        elif total >= 40:
            level = "standard"
        else:
            level = "nurture"

        # 分配Agent
        agent = REGION_AGENTS.get(region_code, "APAC_Sales")

        return {
            "score": total,
            "level": level,
            "region": region_code,
            "agent": agent,
            "dimensions": dimensions,
            "reasons": reasons,
            "customer_id": customer_id,
            "customer_name": name,
        }

    def route_lead_global(self, customer_id: int,
                          customer_data: Optional[dict] = None) -> dict:
        """全球路由决策

        Args:
            customer_id: 客户ID
            customer_data: 可选

        Returns:
            dict: {score, level, region, agent, strategy, priority, action, reasons}
        """
        scored = self.score_lead_global(customer_id, customer_data)

        if "error" in scored:
            return scored

        score = scored["score"]
        level = scored["level"]
        region = scored.get("region", "APAC")
        agent = scored.get("agent", "APAC_Sales")

        # 策略选择
        if score >= 70:
            strategy = "premium_outreach"
            priority = "high"
            action = "立即最高优先级触达 — 个性化报价 + 案例分享"
        elif score >= 40:
            strategy = "standard_followup"
            priority = "medium"
            action = "标准触达流程 — 首条招呼 + 3轮跟进"
        else:
            strategy = "nurture_sequence"
            priority = "low"
            action = "培育序列 — 低频率触达 + 定向内容推送"

        # 区域特定策略
        if region == "NA":
            strategy += "_na"
            action += " | NA策略：强调品质 + 交期保障"
        elif region == "EU":
            strategy += "_eu"
            action += " | EU策略：强调环保认证 + 合规"
        elif region == "APAC":
            strategy += "_apac"
            action += " | APAC策略：强调性价比 + 快速出货"
        elif region == "LATAM":
            strategy += "_latam"
            action += " | LATAM策略：强调价格优势 + 灵活支付"
        elif region == "MEA":
            strategy += "_mea"
            action += " | MEA策略：强调定制能力 + 长期合作"

        return {
            "score": score,
            "level": level,
            "region": region,
            "agent": agent,
            "strategy": strategy,
            "priority": priority,
            "action": action,
            "dimensions": scored.get("dimensions", {}),
            "reasons": scored.get("reasons", []),
            "customer_id": customer_id,
            "customer_name": scored.get("customer_name", ""),
        }

    def batch_route_global(self, customer_ids: list) -> list:
        """批量路由

        Returns:
            list: [route_result, ...]
        """
        results = []
        for cid in customer_ids:
            try:
                results.append(self.route_lead_global(cid))
            except Exception as e:
                results.append({"customer_id": cid, "error": str(e)})
        return results

    def export_lead_analysis(self, limit: int = 50) -> list:
        """导出所有线索的全球评分分析

        Returns:
            list: [{id, name, company, country, score, region, agent, level}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            conn.row_factory = None
            rows = conn.execute(
                "SELECT id, name, company, country, source, notes, lead_score, lead_status FROM customers LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()

            results = []
            for row in rows:
                customer_data = {
                    "name": row[1] or "",
                    "company": row[2] or "",
                    "country": row[3] or "",
                    "source": row[4] or "",
                    "notes": row[5] or "",
                }
                scored = self.score_lead_global(row[0], customer_data)
                results.append({
                    "id": row[0],
                    "name": row[1],
                    "company": row[2],
                    "country": row[3],
                    "score": scored.get("score", 0),
                    "region": scored.get("region", ""),
                    "agent": scored.get("agent", ""),
                    "level": scored.get("level", ""),
                    "current_status": row[7],
                })
            return results
        except Exception:
            return []

    def _detect_industry(self, text: str) -> str:
        """从文本检测行业"""
        keywords = {
            "restaurant": ["restaurant", "cafe", "coffee", "pizza", "grill",
                          "bar", "pub", "food", "diner", "kitchen", "bakery",
                          "catering", "bistro", "brewery", "steakhouse"],
            "hotel": ["hotel", "inn", "resort", "hostel", "lodge", "motel",
                     "guesthouse", "holiday inn", "marriott", "hilton"],
            "retail": ["store", "shop", "retail", "boutique", "market", "mall",
                      "supermarket", "grocery", "department store", "outlet",
                      "convenience store", "plaza"],
            "salon": ["salon", "spa", "beauty", "barber", "nail", "hair",
                     "cosmetic", "wellness", "massage", "facial"],
            "office": ["office", "corp", "inc", "ltd", "llc", "professional",
                      "agency", "firm", "headquarters", "co-working"],
            "warehouse": ["warehouse", "factory", "manufacturing", "industrial",
                         "logistics", "storage", "distribution"],
        }
        text_lower = text.lower()
        for industry, kws in keywords.items():
            if any(kw in text_lower for kw in kws):
                return industry
        return "other"


# ==================== 测试 ====================
if __name__ == "__main__":
    router = GlobalLeadRouter()

    # 模拟测试数据
    test_cases = [
        {"id": 1, "name": "Pizza Hut NYC", "company": "Pizza Hut", "country": "US",
         "source": "inquiry", "notes": "Need LED sign for new restaurant opening"},
        {"id": 2, "name": "Hotel Berlin", "company": "Marriott", "country": "DE",
         "source": "import", "notes": "Looking for illuminated signage"},
        {"id": 3, "name": "Tokyo Store", "company": "7-Eleven JP", "country": "JP",
         "source": "scrape", "notes": "Storefront sign inquiry"},
        {"id": 4, "name": "Sao Paulo Shop", "company": "Local Boutique", "country": "BR",
         "source": "scrape", "notes": ""},
    ]

    print("=== Global Lead Routing ===")
    for tc in test_cases:
        result = router.route_lead_global(tc["id"], tc)
        print(f"\n  [{tc['country']}] {tc['name']}:")
        print(f"    Score: {result.get('score', '?')} → {result.get('level', '?')}")
        print(f"    Region: {result.get('region', '?')} → Agent: {result.get('agent', '?')}")
        print(f"    Priority: {result.get('priority', '?')}")
