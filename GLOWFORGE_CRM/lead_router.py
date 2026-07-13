"""Lead Router — 客户线索路由引擎

线索从各个来源进入系统后的统一路由：评分 → 分级 → 分配策略。
"""

import re
import os
import csv
import sys
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ==================== 评分权重 ====================

_SCORE_WEIGHTS = {
    "country": {
        "US": 20, "USA": 20, "United States": 20,
        "UK": 18, "GB": 18, "United Kingdom": 18,
        "AU": 18, "Australia": 18,
        "CA": 18, "Canada": 18,
        "DE": 16, "Germany": 16,
        "FR": 16, "France": 16,
        "IT": 14, "ES": 14, "NL": 14,
        "JP": 14, "Japan": 14,
        "SG": 14, "Singapore": 14,
    },
    "industry": {
        "restaurant": 15, "restaurant chain": 15,
        "hotel": 15,
        "retail": 12, "store": 12, "shop": 12,
        "bar": 12, "club": 12,
        "office": 8, "corporate": 8,
        "warehouse": 5, "factory": 5,
    },
    "source": {
        "inquiry": 25,  # 主动询价
        "referral": 20,  # 推荐
        "import": 15,  # 导入列表
        "scrape": 10,  # 爬取
        "manual": 15,  # 手动添加
    },
    "demand_keywords": [
        (r"\bled\b", 5),
        (r"\bsign\b", 5),
        (r"\billuminate", 4),
        (r"\bchannel\s+letter", 5),
        (r"\bneon\b", 3),
        (r"\bstorefront\b", 4),
        (r"\bacrylic\b", 3),
        (r"\bfront[\s-]?glow\b", 4),
        (r"\bbacklit|back-lit\b", 4),
        (r"\border\b", 8),
        (r"\bquote\b", 5),
        (r"\bprice\b", 5),
        (r"\bcost\b", 3),
        (r"\bshipp\w+\b", 3),
        (r"\bbusiness\b", 2),
    ],
}


class LeadRouter:
    """线索路由引擎"""

    def import_csv(self, filepath: str) -> dict:
        """导入CSV线索文件

        CSV格式要求:
            name, company, whatsapp, country, industry, source, campaign, notes
            至少需要 name 或 whatsapp 其中一项

        Returns:
            dict: {imported: int, skipped: int, errors: [str]}
        """
        rows = []
        errors = []
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    name = (row.get("name") or "").strip()
                    whatsapp = (row.get("whatsapp") or "").strip()
                    if not name and not whatsapp:
                        errors.append(f"Row {i+2}: missing both name and whatsapp")
                        continue
                    rows.append({
                        "name": name,
                        "company": (row.get("company") or "").strip(),
                        "whatsapp": whatsapp,
                        "country": (row.get("country") or "").strip().upper(),
                        "language": "English",
                        "status": "new",
                        "source": (row.get("source") or "import").strip(),
                        "campaign": (row.get("campaign") or "").strip(),
                        "lead_status": "new",
                        "notes": (row.get("notes") or "").strip(),
                    })
        except Exception as e:
            return {"imported": 0, "skipped": 0, "errors": [f"File error: {e}"]}

        if not rows:
            return {"imported": 0, "skipped": 0, "errors": errors or ["No valid rows found"]}

        # 批量导入
        try:
            sys.path.insert(0, BASE_DIR)
            from database import bulk_add_customers
            imported, skipped, db_errors = bulk_add_customers(rows)
            errors.extend(db_errors)
            return {"imported": imported, "skipped": skipped, "errors": errors}
        except Exception as e:
            return {"imported": 0, "skipped": 0, "errors": [f"DB error: {e}"]}

    def score_lead(self, customer_id: int, customer_data: dict = None) -> dict:
        """对单个线索评分

        Args:
            customer_id: 客户ID
            customer_data: 可选的客户数据dict，避免重复数据库查询
                {country, company, notes, source, campaign, lead_status}

        Returns:
            dict: {score: int, level: str, reason: str}
        """
        score = 0
        reasons = []

        if customer_data is None:
            try:
                sys.path.insert(0, BASE_DIR)
                from database import get_customer
                cust = get_customer(customer_id)
                if not cust:
                    return {"score": 0, "level": "unknown", "reason": "Customer not found"}
                customer_data = cust
            except Exception:
                return {"score": 0, "level": "unknown", "reason": "Customer not found"}

        # 1. 国家评分
        country = (customer_data.get("country") or "").upper()
        for key, weight in _SCORE_WEIGHTS["country"].items():
            if country == key.upper() or country[:2] == key[:2]:
                score += weight
                reasons.append(f"country({country}): +{weight}")
                break

        # 2. 行业/公司关键词评分
        company = (customer_data.get("company") or "").lower()
        notes = (customer_data.get("notes") or "").lower()
        combined_text = f"{company} {notes}"
        for key, weight in _SCORE_WEIGHTS["industry"].items():
            if key in combined_text:
                score += weight
                reasons.append(f"industry({key}): +{weight}")
                break

        # 3. 来源评分
        source = (customer_data.get("source") or "").lower()
        for key, weight in _SCORE_WEIGHTS["source"].items():
            if key in source or source in key:
                score += weight
                reasons.append(f"source({source}): +{weight}")
                break

        # 4. 需求关键词评分
        for pattern, weight in _SCORE_WEIGHTS["demand_keywords"]:
            if re.search(pattern, combined_text):
                score += weight
                reasons.append(f"keyword({pattern}): +{weight}")

        # 5. 已成交客户加分
        lead_status = customer_data.get("lead_status", "")
        if lead_status == "customer":
            score = min(score + 20, 100)
            reasons.append("existing customer: +20")

        # 分级
        score = min(max(score, 0), 100)
        if score >= 70:
            level = "high"
        elif score >= 40:
            level = "medium"
        else:
            level = "low"

        return {
            "score": score,
            "level": level,
            "reason": "; ".join(reasons) if reasons else "default score",
        }

    def route_lead(self, customer_id: int, customer_data: dict = None) -> dict:
        """路由线索到合适的销售策略

        Returns:
            dict: {score, level, agent, strategy, priority}
        """
        result = self.score_lead(customer_id, customer_data)
        score = result["score"]
        level = result["level"]

        if score >= 70:
            agent = "EN_Sales_01"
            strategy = "premium"
            priority = "high"
        elif score >= 40:
            agent = "EN_Sales_02"
            strategy = "standard"
            priority = "medium"
        else:
            agent = "NURTURE_AI"
            strategy = "nurture"
            priority = "low"

        return {
            "score": score,
            "level": level,
            "agent": agent,
            "strategy": strategy,
            "priority": priority,
            "reason": result["reason"],
        }

    def route_lead_v5(self, customer_id: int,
                       customer_data: dict = None) -> dict:
        """V5 全球路由（委托给 GlobalLeadRouter）

        Returns:
            dict: {score, level, region, agent, strategy, priority, action, reasons}
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from global_lead_router import GlobalLeadRouter
            router = GlobalLeadRouter()
            return router.route_lead_global(customer_id, customer_data)
        except ImportError:
            # 回退到 V4 路由
            return self.route_lead(customer_id, customer_data)
        except Exception as e:
            return {"error": str(e)}

    def score_batch(self, customer_ids: list) -> list:
        """批量评分并排序

        Returns:
            list: [{customer_id, score, level, agent, priority}, ...] 按score降序
        """
        results = []
        for cid in customer_ids:
            r = self.route_lead(cid)
            results.append({"customer_id": cid, **r})
        results.sort(key=lambda x: -x["score"])
        return results


# ==================== 测试 ====================
if __name__ == "__main__":
    r = LeadRouter()

    # 模拟评分测试
    test_leads = [
        {"country": "US", "company": "NY Grill Restaurant", "notes": "needs LED sign for storefront", "source": "inquiry"},
        {"country": "JP", "company": "Tokyo Office", "notes": "needs acrylic letters", "source": "import"},
        {"country": "BR", "company": "Loja Center", "notes": "browsing", "source": "scrape"},
    ]

    print("=== Lead Scoring ===")
    for i, data in enumerate(test_leads):
        # 模拟数据库查询返回格式
        result = r.score_lead(i + 1, data)
        route = r.route_lead(i + 1, data)
        print(f"  Lead {i+1}: score={result['score']}, level={result['level']}, agent={route['agent']}")
        print(f"    Reason: {result['reason']}")
