"""Campaign Engine — 批量沉睡客户唤醒系统

客户池分组:
  - quoted_no_response: 已报价无回应
  - old_inquiries: 老询盘
  - high_score_dormant: 高分沉默客户
"""
import os
import sys
import sqlite3
import logging
import random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
from ai_overlay.crm_bridge import search_customers, get_customer

logger = logging.getLogger("campaign")

# ── 客户细分查询 ────────────────────────────────────────

def _query(sql, params=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params or []).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── 客户池采集器 ────────────────────────────────────────

SEGMENTS = {
    "quoted_no_response": {
        "name": "已报价未回复",
        "sql": """
            SELECT DISTINCT c.id, c.name, c.country
            FROM customers c
            JOIN quotes q ON q.customer_id = c.id
            WHERE q.status = 'sent'
            AND c.id NOT IN (
                SELECT customer_id FROM messages
                WHERE direction = 'received'
                AND created_at > datetime('now', '-7 days')
            )
            AND c.lead_state IN ('PRICING', 'FOLLOWUP')
            LIMIT 50
        """,
        "templates": [
            "Hi {name}, just following up on the quote I sent. Happy to adjust if needed!",
            "{name}, any thoughts on the quotation? We're flexible on quantities.",
            "Quick check-in, {name} — is the pricing working for you?",
        ],
    },
    "old_inquiries": {
        "name": "老询盘",
        "sql": """
            SELECT id, name, country FROM customers
            WHERE created_at < datetime('now', '-14 days')
            AND lead_state IN ('QUALIFYING', 'NEW')
            AND id NOT IN (
                SELECT customer_id FROM messages
                WHERE direction = 'received'
                AND created_at > datetime('now', '-14 days')
            )
            LIMIT 50
        """,
        "templates": [
            "Hi {name}, it's been a while! We have some new products you might like.",
            "{name}, are you still looking for signage solutions? We've updated our catalog.",
            "Hello {name}, wondering if you're still in the market. Happy to help!",
        ],
    },
    "high_score_dormant": {
        "name": "高分沉默客户",
        "sql": """
            SELECT id, name, country FROM customers
            WHERE lead_score >= 50
            AND lead_state IN ('FOLLOWUP', 'COLD')
            AND id NOT IN (
                SELECT customer_id FROM messages
                WHERE direction = 'received'
                AND created_at > datetime('now', '-30 days')
            )
            ORDER BY lead_score DESC
            LIMIT 30
        """,
        "templates": [
            "Hi {name}, haven't heard from you in a while! We're running a special offer this month.",
            "{name}, we've expanded our product line — would love to show you what's new.",
            "Hello {name}, just a friendly reminder that we're here whenever you need quality signage.",
        ],
    },
}


# ── 广播引擎 ────────────────────────────────────────────

class CampaignEngine:
    """批量唤醒引擎"""

    def __init__(self):
        self._logs = []

    def list_segments(self):
        """列出所有客户池及数量"""
        result = {}
        for key, seg in SEGMENTS.items():
            try:
                rows = _query(seg["sql"])
                result[key] = {
                    "name": seg["name"],
                    "count": len(rows),
                    "sample": [{"id": r["id"], "name": r["name"]} for r in rows[:3]],
                }
            except Exception as e:
                result[key] = {"name": seg["name"], "error": str(e)}
        return result

    def execute_segment(self, segment_key, dry_run=True):
        """执行一个客户池的唤醒广播

        参数:
            segment_key: 客户池名称
            dry_run: True=仅预览, False=实际发送

        返回:
            dict: {segment, total, sent, failed, messages: [{customer, message}]}
        """
        seg = SEGMENTS.get(segment_key)
        if not seg:
            return {"error": f"未知客户池: {segment_key}"}

        rows = _query(seg["sql"])
        templates = seg["templates"]
        results = []

        for row in rows:
            # 个性化
            name = row.get("name", "Customer")
            template = random.choice(templates)
            message = template.replace("{name}", name)

            if row.get("country"):
                # 不同国家可用不同语气（简化版）
                pass

            entry = {
                "customer_id": row["id"],
                "customer_name": name,
                "message": message,
            }

            if not dry_run:
                try:
                    from ai_overlay.crm_bridge import send_whatsapp
                    resp = send_whatsapp(message, name)
                    entry["status"] = "sent" if resp.get("ok", True) else "failed"
                except Exception as e:
                    entry["status"] = "failed"
                    entry["error"] = str(e)
            else:
                entry["status"] = "preview"

            results.append(entry)

        sent = sum(1 for r in results if r["status"] == "sent")
        failed = sum(1 for r in results if r["status"] == "failed")

        logger.info(
            f"[Campaign] {seg['name']}: "
            f"{'预览' if dry_run else '发送'} {len(results)} 条 "
            f"(成功{sent}/失败{failed})"
        )

        return {
            "segment": seg["name"],
            "segment_key": segment_key,
            "total": len(results),
            "sent": sent,
            "failed": failed,
            "dry_run": dry_run,
            "messages": results,
        }

    def execute_all(self, dry_run=True):
        """执行所有客户池的广播"""
        results = {}
        for key in SEGMENTS:
            results[key] = self.execute_segment(key, dry_run=dry_run)
        return results


# ── 快捷函数 ────────────────────────────────────────────

def preview_segment(segment_key):
    """预览客户池"""
    eng = CampaignEngine()
    return eng.execute_segment(segment_key, dry_run=True)


def run_campaign(segment_key):
    """实际发送广播"""
    eng = CampaignEngine()
    return eng.execute_segment(segment_key, dry_run=False)
