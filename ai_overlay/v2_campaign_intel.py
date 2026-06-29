"""V2.0 Campaign Intelligence — 智能营销引擎

6个智能客户池（扩展原有 campaign.py 的3个池）:
  1. HOT_NO_RESPONSE   — 高意向沉默客户
  2. QUOTED_NO_REPLY   — 已报价未回复
  3. OLD_CUSTOMERS     — 老客户复购唤醒
  4. PRICE_SENSITIVE   — 价格敏感客户
  5. HIGH_MARGIN_TARGET — 高利润目标客户
  6. DORMANT_HIGH_SCORE — 高分沉睡客户

每个池关联: SQL 查询 + 营销话术模板 + 利润感知策略

复用: campaign.py 的执行模式 + revenue_pressure.py 紧迫感

约束:
  - 默认 dry_run=True
  - 纯 SQL 查询，不调 AI API
"""
import os
import sys
import json
import sqlite3
import logging
import random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
logger = logging.getLogger("v2_campaign_intel")

# ── 6个智能客户池定义 ─────────────────────────────────────

SEGMENTS = {
    "hot_no_response": {
        "name": "高意向沉默客户",
        "description": "有高意向但短期内无回复的客户",
        "sql": """
            SELECT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            WHERE c.lead_score >= 60
              AND c.lead_state IN ('PRICING', 'NEGOTIATING', 'HOT')
              AND c.id NOT IN (
                  SELECT customer_id FROM messages
                  WHERE direction='received'
                    AND created_at >= datetime('now', '-3 days')
              )
            ORDER BY c.lead_score DESC
            LIMIT 30
        """,
        "templates": [
            "Hi {name}, just checking in! We have a production slot opening this week. "
             "Want me to reserve it for your order?",
            "{name}, I noticed you were interested in our LED signs. "
             "We're running a limited-time offer — let me know if you'd like to hear about it.",
            "Hey {name}, quick update — we just finished a similar project for another client "
             "and the result was amazing. Still interested?",
        ],
        "strategy": "urgency_push",
    },
    "quoted_no_reply": {
        "name": "已报价未回复",
        "description": "已发送报价但7天内未回复",
        "sql": """
            SELECT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            WHERE c.lead_state IN ('PRICING', 'FOLLOWUP')
              AND c.id NOT IN (
                  SELECT customer_id FROM messages
                  WHERE direction='received'
                    AND created_at >= datetime('now', '-7 days')
              )
            ORDER BY c.lead_score DESC
            LIMIT 50
        """,
        "templates": [
            "Hi {name}, I sent over the quote a few days ago. "
             "Do you have any questions I can help with? Happy to adjust if needed.",
            "{name}, just following up on the quotation. "
             "We can be flexible on quantity and delivery timeline.",
            "Hey {name}, the price I quoted is valid until end of month. "
             "Let me know if you'd like to proceed!",
        ],
        "strategy": "price_reminder",
    },
    "old_customers": {
        "name": "老客户复购唤醒",
        "description": "有成交记录但长期未联系的老客户",
        "sql": """
            SELECT DISTINCT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            WHERE o.status IN ('shipped', 'delivered', 'completed')
              AND c.id NOT IN (
                  SELECT customer_id FROM messages
                  WHERE direction='received'
                    AND created_at >= datetime('now', '-60 days')
              )
            ORDER BY o.created_at DESC
            LIMIT 30
        """,
        "templates": [
            "Hi {name}, hope the signage is working great! "
             "We just launched new products — brighter LEDs and energy-saving options.",
            "{name}, it's been a while! We have new colors and sizes available now. "
             "Want to see the latest catalog?",
            "Hey {name}, as our valued customer, I'd like to offer you "
             "an exclusive discount on your next order. Let me know!",
        ],
        "strategy": "upsell_new_product",
    },
    "price_sensitive": {
        "name": "价格敏感客户",
        "description": "多次询问价格/折扣，价格敏感型客户",
        "sql": """
            SELECT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            WHERE c.id IN (
                SELECT customer_id FROM messages
                WHERE (content_en LIKE '%expensive%'
                    OR content_en LIKE '%cheaper%'
                    OR content_en LIKE '%discount%'
                    OR content_en LIKE '%too much%'
                    OR content_en LIKE '%better price%')
                GROUP BY customer_id
                HAVING COUNT(*) >= 2
            )
            ORDER BY c.lead_score DESC
            LIMIT 20
        """,
        "templates": [
            "Hi {name}, I understand budget is important. "
             "Let me show you our most cost-effective option with the best value.",
            "{name}, we have an economy line that might fit your budget better. "
             "Same quality, simpler design = lower price.",
            "Hey {name}, for the quantity you need, I can offer a volume discount. "
             "Let me prepare a customized quote for you.",
        ],
        "strategy": "value_anchor",
    },
    "high_margin_target": {
        "name": "高利润目标客户",
        "description": "高利润国家/高意向客户",
        "sql": """
            SELECT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            WHERE c.country IN ('US', 'AE', 'SA', 'GB', 'DE', 'AU', 'CA', 'CH', 'SG', 'JP')
              AND c.lead_score >= 40
              AND c.lead_state NOT IN ('CLOSED_WON', 'CLOSED_LOST', 'COLD')
            ORDER BY c.lead_score DESC
            LIMIT 25
        """,
        "templates": [
            "Hi {name}, as a premium client, I'd like to offer you "
             "our express production service — 30% faster delivery.",
            "{name}, we have a VIP package that includes custom design support "
             "and priority shipping. Interested?",
            "Hey {name}, for clients in {country}, we offer additional warranty options. "
             "Let me send you the details.",
        ],
        "strategy": "premium_push",
    },
    "dormant_high_score": {
        "name": "高分沉睡客户",
        "description": "曾经高意向但长期无互动",
        "sql": """
            SELECT c.id, c.name, c.country, c.lead_score, c.lead_state
            FROM customers c
            WHERE c.lead_score >= 50
              AND c.lead_state IN ('FOLLOWUP', 'COLD')
              AND c.id NOT IN (
                  SELECT customer_id FROM messages
                  WHERE direction='received'
                    AND created_at >= datetime('now', '-30 days')
              )
            ORDER BY c.lead_score DESC
            LIMIT 20
        """,
        "templates": [
            "Hi {name}, it's been quiet! Just wanted to share our new arrivals — "
             "we've added some exciting new designs to the collection.",
            "{name}, I'm checking back in to see if your needs have changed. "
             "We've updated our catalog and pricing.",
            "Hey {name}, hope everything's going well! "
             "Since we last spoke, we've improved our production efficiency "
             "and can now offer better lead times.",
        ],
        "strategy": "friendly_reminder",
    },
}


class CampaignIntelEngine:
    """智能营销引擎 — 利润感知的客户池营销"""

    @staticmethod
    def list_segments():
        """列出所有客户池及预估数量"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        results = {}
        for key, seg in SEGMENTS.items():
            try:
                count = conn.execute(f"SELECT COUNT(*) as cnt FROM ({seg['sql']})").fetchone()["cnt"]
                sample_rows = conn.execute(seg["sql"]).fetchall()[:3]
                sample = [{"id": r["id"], "name": r["name"]} for r in sample_rows]
            except Exception as e:
                count = 0
                sample = []
                logger.warning(f"Segment {key} SQL error: {e}")
            results[key] = {
                "name": seg["name"],
                "description": seg["description"],
                "count": count,
                "sample": sample,
                "strategy": seg["strategy"],
            }
        conn.close()
        return results

    @staticmethod
    def execute_segment(segment_key, dry_run=True):
        """执行指定客户池的营销

        参数:
            segment_key: 客户池 key
            dry_run: True=仅预览不发送, False=实际发送WhatsApp

        返回:
            dict: { segment, key, total, sent, failed, dry_run, messages }
        """
        if segment_key not in SEGMENTS:
            return {"error": f"Unknown segment: {segment_key}"}

        seg = SEGMENTS[segment_key]
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(seg["sql"]).fetchall()
        except Exception as e:
            conn.close()
            return {"error": str(e), "segment": segment_key, "total": 0}

        customers = [dict(r) for r in rows]
        conn.close()

        messages = []
        sent_count = 0
        fail_count = 0

        for cust in customers:
            template = random.choice(seg["templates"])
            message = template.format(
                name=cust.get("name", "Customer"),
                country=cust.get("country", ""),
            )

            entry = {
                "customer_id": cust["id"],
                "customer_name": cust["name"],
                "message": message,
                "status": "preview" if dry_run else "pending",
            }

            if not dry_run:
                try:
                    from ai_overlay.crm_bridge import send_whatsapp
                    resp = send_whatsapp(message, cust["name"])
                    if resp and resp.get("ok", True):
                        entry["status"] = "sent"
                        sent_count += 1
                    else:
                        entry["status"] = "failed"
                        entry["error"] = str(resp)
                        fail_count += 1
                except Exception as e:
                    entry["status"] = "failed"
                    entry["error"] = str(e)
                    fail_count += 1
            else:
                sent_count += 1  # 预览模式算作成功预览

            messages.append(entry)

        return {
            "segment": seg["name"],
            "key": segment_key,
            "strategy": seg["strategy"],
            "total": len(customers),
            "sent": sent_count if dry_run else sent_count,
            "failed": fail_count,
            "dry_run": dry_run,
            "messages": messages,
        }

    @staticmethod
    def execute_all(dry_run=True):
        """执行所有客户池"""
        results = {}
        for key in SEGMENTS:
            logger.info(f"Campaign segment: {key} (dry_run={dry_run})")
            results[key] = CampaignIntelEngine.execute_segment(key, dry_run=dry_run)
        return results

    @staticmethod
    def get_segment_strategy(segment_key):
        """获取客户池的推荐策略"""
        strategies = {
            "urgency_push": {
                "label": "紧迫感推进",
                "pressure_tier": "medium",
                "goal": "促使沉默客户回复",
                "best_time": "工作时间",
            },
            "price_reminder": {
                "label": "价格提醒+稀缺性",
                "pressure_tier": "soft",
                "goal": "提醒报价有效期，促使成交",
                "best_time": "报价后第3-5天",
            },
            "upsell_new_product": {
                "label": "新品/升级推荐",
                "pressure_tier": None,
                "goal": "老客户复购/升级消费",
                "best_time": "上次购买后60-90天",
            },
            "value_anchor": {
                "label": "价值锚定",
                "pressure_tier": "soft",
                "goal": "价格敏感客户价值教育",
                "best_time": "砍价对话后",
            },
            "premium_push": {
                "label": "高端推荐",
                "pressure_tier": None,
                "goal": "高利润客户增值服务",
                "best_time": "销售初期",
            },
            "friendly_reminder": {
                "label": "友好唤醒",
                "pressure_tier": None,
                "goal": "唤醒沉眠客户",
                "best_time": "非工作时间前",
            },
        }
        seg = SEGMENTS.get(segment_key, {})
        return strategies.get(seg.get("strategy"), {})
