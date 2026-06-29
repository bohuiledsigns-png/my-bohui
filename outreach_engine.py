"""Outreach Engine — 自动触达引擎

执行"主动触达 + 自动跟进"：从数据导入到首条WhatsApp消息发送，
再到多轮跟进的时间表管理。
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ==================== 触达节奏定义 ====================

OUTREACH_SEQUENCE = [
    {"day": 0, "step": "first_contact", "label": "首条招呼"},
    {"day": 1, "step": "followup_1", "label": "温和提醒"},
    {"day": 3, "step": "followup_2", "label": "案例分享"},
    {"day": 7, "step": "followup_3", "label": "价值重申"},
    {"day": 14, "step": "followup_4", "label": "最后跟进"},
    {"day": 30, "step": "cold", "label": "进入冷线索池"},
]

# 跟进模板（可被AI个性化改写）
FOLLOWUP_TEMPLATES = {
    "first_contact": (
        "Hi {name}, this is {sales_name} from Bohui GLOWFORGE — "
        "we manufacture custom illuminated signage for {industry} businesses "
        "and ship worldwide. "
        "Do you currently have a storefront sign, or are you planning a new one?"
    ),
    "followup_1": (
        "Hi {name}, just checking in — did you have a chance to see my message? "
        "Happy to answer any questions about our signage solutions for {industry} businesses."
    ),
    "followup_2": (
        "Hi {name}, thought you might find this useful — "
        "here is a similar {industry} sign project we recently completed. "
        "If you want, I can prepare a quick concept for your storefront.\n\n"
        "No pressure at all — just wanted to share."
    ),
    "followup_3": (
        "Hi {name}, just a quick update — we are currently running a special "
        "on illuminated signage for {industry} businesses. "
        "If your timing is right, I can offer priority production scheduling "
        "and a free design concept.\n\n"
        "Let me know if you are interested!"
    ),
    "followup_4": (
        "Hi {name}, wanted to touch base one last time. "
        "If the timing is not right yet, no worries at all. "
        "My door is always open when you are ready.\n\n"
        "Wishing you success with your {industry}!"
    ),
}


class OutreachEngine:
    """自动触达引擎"""

    def __init__(self):
        self.sequence = OUTREACH_SEQUENCE
        self.templates = FOLLOWUP_TEMPLATES

    def process_new_leads(self, limit: int = 10) -> dict:
        """处理待触达线索：评分 → 路由 → 发送首条招呼

        Args:
            limit: 本次处理的最大线索数

        Returns:
            dict: {processed: int, sent: int, skipped: int, errors: [str]}
        """
        processed = 0
        sent = 0
        skipped = 0
        errors = []

        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_leads, update_last_contacted, update_lead_status
            from lead_router import LeadRouter
        except ImportError as e:
            return {"processed": 0, "sent": 0, "skipped": 0, "errors": [f"Import error: {e}"]}

        # 获取所有 lead_status='new' 的线索
        leads = get_leads(status="new", limit=limit)
        if not leads:
            return {"processed": 0, "sent": 0, "skipped": 0, "errors": []}

        router = LeadRouter()

        for lead in leads:
            processed += 1
            try:
                # 评分 + 路由
                routing = router.route_lead(lead["id"], lead)

                # 只对高/中优先级发送首条触达
                if routing["priority"] == "low":
                    skipped += 1
                    update_lead_status(lead["id"], "cold")
                    continue

                # 生成首条消息
                name = lead.get("name", "there")
                industry = self._detect_industry(lead.get("company", "") or "",
                                                  lead.get("notes", "") or "")
                msg = self.templates["first_contact"].format(
                    name=name,
                    sales_name="Philip",
                    industry=industry,
                )

                # 发送 WhatsApp 消息
                whatsapp_sent = self._send_whatsapp(msg, name)

                if whatsapp_sent:
                    sent += 1
                    update_last_contacted(lead["id"])
                    update_lead_status(lead["id"], "contacted")
                else:
                    skipped += 1
                    errors.append(f"Lead {lead['id']}: WhatsApp send failed")

            except Exception as e:
                errors.append(f"Lead {lead['id']}: {e}")
                skipped += 1

        return {
            "processed": processed,
            "sent": sent,
            "skipped": skipped,
            "errors": errors,
        }

    def schedule_followups(self, limit: int = 20) -> dict:
        """检查并发送到期的跟进

        使用 database.get_leads_due_followup() 获取到期待跟进线索。

        Returns:
            dict: {checked: int, sent: int, skipped: int, errors: [str]}
        """
        checked = 0
        sent = 0
        skipped = 0
        errors = []

        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_leads_due_followup, update_last_contacted
        except ImportError as e:
            return {"checked": 0, "sent": 0, "skipped": 0, "errors": [f"Import error: {e}"]}

        due_leads = get_leads_due_followup()
        if not due_leads:
            return {"checked": 0, "sent": 0, "skipped": 0, "errors": []}

        for lead in due_leads[:limit]:
            checked += 1
            try:
                followup_type = lead.get("followup_type", "")
                days_since = lead.get("days_since", 0)

                # 确定跟进步骤
                if days_since >= 30:
                    step = "followup_4"  # 最后跟进
                elif days_since >= 14:
                    step = "followup_4"
                elif days_since >= 7:
                    step = "followup_3"
                elif days_since >= 3:
                    step = "followup_2"
                else:
                    step = "followup_1"

                template = self.templates.get(step)
                if not template:
                    skipped += 1
                    continue

                name = lead.get("name", "there")
                industry = self._detect_industry(
                    lead.get("company", "") or "",
                    ""
                )
                msg = template.format(name=name, sales_name="Philip", industry=industry)

                # 发送
                whatsapp_sent = self._send_whatsapp(msg, name)
                if whatsapp_sent:
                    sent += 1
                    update_last_contacted(lead["id"])
                else:
                    skipped += 1

            except Exception as e:
                errors.append(f"Lead {lead['id']}: {e}")
                skipped += 1

        return {
            "checked": checked,
            "sent": sent,
            "skipped": skipped,
            "errors": errors,
        }

    def get_due_followups(self, limit: int = 20) -> list:
        """获取需要跟进的线索列表

        Returns:
            list: [{customer_id, name, company, country, days_since, followup_step}, ...]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_leads_due_followup
        except ImportError:
            return []

        due = get_leads_due_followup()
        results = []
        for lead in due[:limit]:
            days = lead.get("days_since", 0)
            if days >= 14:
                step = "followup_4"
            elif days >= 7:
                step = "followup_3"
            elif days >= 3:
                step = "followup_2"
            else:
                step = "followup_1"

            results.append({
                "customer_id": lead["id"],
                "name": lead.get("name", ""),
                "company": lead.get("company", ""),
                "country": lead.get("country", ""),
                "days_since": days,
                "followup_step": step,
            })

        return results

    def _send_whatsapp(self, text: str, contact_name: str) -> bool:
        """发送 WhatsApp 消息（模拟或实际）

        实际使用时接入 whatsapp_engine.send_text。
        当前返回 True 模拟成功（测试用）。
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from whatsapp_engine import send_text
            send_text(text, contact_name=contact_name)
            return True
        except ImportError:
            # 模拟模式 — 测试用
            return True
        except Exception:
            return False

    def _detect_industry(self, company: str, notes: str) -> str:
        """从公司名和备注检测行业"""
        text = f"{company} {notes}".lower()
        keywords = {
            "restaurant": ["restaurant", "cafe", "coffee", "pizza", "grill", "bar", "pub", "food", "diner", "kitchen"],
            "retail": ["store", "shop", "retail", "boutique", "market", "mall"],
            "hotel": ["hotel", "inn", "resort", "hostel", "lodge"],
            "office": ["office", "corp", "inc", "ltd", "llc", "professional"],
            "salon": ["salon", "spa", "beauty", "barber", "nail"],
        }
        for industry, kws in keywords.items():
            if any(kw in text for kw in kws):
                return industry
        return "storefront"


# ==================== 测试 ====================
if __name__ == "__main__":
    engine = OutreachEngine()

    print("=== Due Followups ===")
    due = engine.get_due_followups(limit=5)
    print(f"Found {len(due)} due followups")
    for d in due:
        print(f"  {d['name']} ({d['country']}): {d['days_since']} days → step {d['followup_step']}")

    print("\n=== Process New Leads ===")
    result = engine.process_new_leads(limit=5)
    print(f"Processed: {result['processed']}, Sent: {result['sent']}, Skipped: {result['skipped']}")

    print("\n=== Schedule Followups ===")
    result2 = engine.schedule_followups(limit=5)
    print(f"Checked: {result2['checked']}, Sent: {result2['sent']}, Skipped: {result2['skipped']}")
