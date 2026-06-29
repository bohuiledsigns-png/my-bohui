"""Campaign Engine — 营销活动引擎

定义和管理"触达活动"：目标国家、行业、话术模板、跟进节奏。
活动数据存储在 crm_data.db 的 campaigns 表中。
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# ==================== 数据库初始化 ====================

_CAMPAIGN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_countries TEXT DEFAULT '[]',
    target_industries TEXT DEFAULT '[]',
    message_template TEXT DEFAULT '',
    max_outreach_per_day INTEGER DEFAULT 10,
    followup_days TEXT DEFAULT '[1,3,7,14,30]',
    followup_templates TEXT DEFAULT '[]',
    status TEXT DEFAULT 'draft',
    total_leads INTEGER DEFAULT 0,
    contacted_leads INTEGER DEFAULT 0,
    replied_leads INTEGER DEFAULT 0,
    converted_leads INTEGER DEFAULT 0,
    revenue_generated REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def ensure_campaigns_table():
    """确保 campaigns 表存在"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_CAMPAIGN_TABLE_SQL)
    conn.commit()
    conn.close()


# ==================== 活动定义 ====================

DEFAULT_FOLLOWUP_TEMPLATES = [
    # Day 1 - 温和提醒
    "Hi {name}, just checking in — did you have a chance to see my message? "
    "Happy to answer any questions about our signage solutions.",
    # Day 3 - 案例分享
    "Hi {name}, thought you might find this useful — "
    "here is a similar {industry} sign project we recently completed. "
    "If you want, I can prepare a quick concept for your storefront.",
    # Day 7 - 价值重申
    "Hi {name}, just a quick update — we are currently running a special "
    "on {product} for {industry} businesses. "
    "If your timing is right, I can offer priority production scheduling.",
    # Day 14 - 最后跟进
    "Hi {name}, wanted to touch base one last time. "
    "If the timing is not right yet, no worries. "
    "My door is always open when you are ready.",
]

DEFAULT_MESSAGE_TEMPLATE = (
    "Hi {name}, this is Philip from Bohui GLOWFORGE — "
    "we manufacture custom illuminated signage for {industry} businesses "
    "and ship worldwide. "
    "Do you currently have a storefront sign, or are you planning a new one?"
)


class Campaign:
    """单个营销活动"""

    def __init__(self, name: str, target_countries: list = None,
                 target_industries: list = None,
                 message_template: str = "",
                 max_outreach_per_day: int = 10):
        self.name = name
        self.target_countries = target_countries or ["US", "UK", "CA", "AU"]
        self.target_industries = target_industries or ["restaurant", "retail", "hotel"]
        self.message_template = message_template or DEFAULT_MESSAGE_TEMPLATE
        self.max_outreach_per_day = max_outreach_per_day
        self.followup_days = [1, 3, 7, 14, 30]
        self.followup_templates = DEFAULT_FOLLOWUP_TEMPLATES
        self.status = "draft"
        self.id = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target_countries": json.dumps(self.target_countries),
            "target_industries": json.dumps(self.target_industries),
            "message_template": self.message_template,
            "max_outreach_per_day": self.max_outreach_per_day,
            "followup_days": json.dumps(self.followup_days),
            "followup_templates": json.dumps(self.followup_templates),
            "status": self.status,
        }


class CampaignEngine:
    """营销活动引擎 — 管理所有活动"""

    def __init__(self):
        ensure_campaigns_table()

    def create_campaign(self, campaign: Campaign) -> int:
        """创建新活动，返回活动ID"""
        conn = sqlite3.connect(DB_PATH)
        data = campaign.to_dict()
        cursor = conn.execute(
            """INSERT INTO campaigns
               (name, target_countries, target_industries, message_template,
                max_outreach_per_day, followup_days, followup_templates, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (data["name"], data["target_countries"], data["target_industries"],
             data["message_template"], data["max_outreach_per_day"],
             data["followup_days"], data["followup_templates"], data["status"])
        )
        campaign.id = cursor.lastrowid
        conn.commit()
        conn.close()
        return campaign.id

    def get_campaign(self, campaign_id: int) -> Optional[dict]:
        """获取活动详情"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_campaigns(self, status: str = None) -> list:
        """列出活动，可选按状态筛选"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE status=? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC"
            ).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def update_status(self, campaign_id: int, status: str):
        """更新活动状态 (draft/active/paused/completed)"""
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE campaigns SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, campaign_id)
        )
        conn.commit()
        conn.close()

    def assign_leads(self, campaign_id: int, customer_ids: list):
        """将线索绑定到活动"""
        conn = sqlite3.connect(DB_PATH)
        for cid in customer_ids:
            conn.execute(
                "UPDATE customers SET campaign=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (f"campaign_{campaign_id}", cid)
            )
        # 更新计数
        conn.execute(
            "UPDATE campaigns SET total_leads=total_leads+?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (len(customer_ids), campaign_id)
        )
        conn.commit()
        conn.close()

    def get_campaign_leads(self, campaign_id: int) -> list:
        """获取活动下的所有线索"""
        try:
            import sys
            sys.path.insert(0, BASE_DIR)
            from database import get_leads
            return get_leads(campaign=f"campaign_{campaign_id}")
        except Exception:
            return []

    def record_reply(self, campaign_id: int):
        """记录一次回复"""
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE campaigns SET replied_leads=replied_leads+1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (campaign_id,)
        )
        conn.commit()
        conn.close()

    def record_conversion(self, campaign_id: int, revenue: float = 0):
        """记录一次转化"""
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """UPDATE campaigns SET
               converted_leads=converted_leads+1,
               revenue_generated=revenue_generated+?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (revenue, campaign_id)
        )
        conn.commit()
        conn.close()

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        for field in ["target_countries", "target_industries", "followup_days", "followup_templates"]:
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d


# ==================== 测试 ====================
if __name__ == "__main__":
    engine = CampaignEngine()

    # 创建活动
    c = Campaign(
        name="US Restaurant Q3",
        target_countries=["US", "CA"],
        target_industries=["restaurant", "fast food"],
        max_outreach_per_day=15,
    )
    cid = engine.create_campaign(c)
    print(f"Created campaign ID: {cid}")

    # 列出活动
    campaigns = engine.list_campaigns()
    print(f"Total campaigns: {len(campaigns)}")
    for camp in campaigns:
        print(f"  [{camp['status']}] {camp['name']} — countries: {camp['target_countries']}")
