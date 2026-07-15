"""Revenue Analytics Engine — 收入分析引擎

回答一个问题: 钱到底是怎么来的?

核心指标:
  1. Funnel Conversion — 各阶段转化率
  2. AI Efficiency — AI回复/followup转化率
  3. Customer Value — LTV/平均订单/国家分布
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

logger = logging.getLogger("analytics")


def _query(sql, params=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params or []).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── 1. 漏斗转化 ─────────────────────────────────────────

def funnel_conversion(days_back=90):
    """获取销售漏斗转化数据

    返回:
        dict: {stages: [{stage, count, pct}], total_leads, won, conversion_rate}
    """
    since = (datetime.now() - timedelta(days=days_back)).isoformat()

    total = _query(
        "SELECT COUNT(*) as c FROM customers WHERE created_at >= ?",
        (since,)
    )[0]["c"]

    stages = []
    stage_config = [
        ("NEW", "新客户"),
        ("QUALIFYING", "意向确认"),
        ("PRICING", "已报价"),
        ("NEGOTIATING", "谈判中"),
        ("CLOSING", "准备成交"),
        ("CLOSED_WON", "已成交"),
    ]

    for state, label in stage_config:
        count = _query(
            "SELECT COUNT(*) as c FROM customers WHERE lead_state=? AND created_at >= ?",
            (state, since)
        )[0]["c"]
        pct = round(count / max(total, 1) * 100, 1)
        stages.append({"state": state, "label": label, "count": count, "pct": pct})

    won = stages[-1]["count"] if stages else 0
    conversion_rate = round(won / max(total, 1) * 100, 1)

    return {
        "period_days": days_back,
        "total_leads": total,
        "won": won,
        "conversion_rate": conversion_rate,
        "stages": stages,
    }


# ── 2. AI 效率 ──────────────────────────────────────────

def ai_efficiency(days_back=30):
    """AI 效率指标

    返回:
        dict: {ai_reply_count, followup_sent, ai_conversion, ...}
    """
    since = (datetime.now() - timedelta(days=days_back)).isoformat()

    # AI 自动回复数
    ai_replies = _query(
        "SELECT COUNT(*) as c FROM messages WHERE direction='sent' AND created_at >= ?",
        (since,)
    )[0]["c"]

    # 客户消息数
    customer_msgs = _query(
        "SELECT COUNT(*) as c FROM messages WHERE direction='received' AND created_at >= ?",
        (since,)
    )[0]["c"]

    # 已成交客户数
    won = _query(
        "SELECT COUNT(*) as c FROM customers WHERE lead_state='CLOSED_WON' AND updated_at >= ?",
        (since,)
    )[0]["c"]

    # 动作日志中的报价动作
    quotes_sent = _query(
        "SELECT COUNT(*) as c FROM lead_action_log "
        "WHERE action IN ('GENERATE_QUOTE','SEND_QUOTE') AND created_at >= ?",
        (since,)
    )[0]["c"]

    # 跟进行为
    followups = _query(
        "SELECT COUNT(*) as c FROM lead_action_log "
        "WHERE action='FOLLOW_UP' AND created_at >= ?",
        (since,)
    )[0]["c"]

    return {
        "period_days": days_back,
        "customer_messages": customer_msgs,
        "ai_replies_sent": ai_replies,
        "quotes_generated": quotes_sent,
        "followups_sent": followups,
        "deals_won": won,
        "ai_response_rate": round(ai_replies / max(customer_msgs, 1), 3),
        "ai_conversion_rate": round(won / max(customer_msgs, 1) * 100, 1),
    }


# ── 3. 客户价值 ─────────────────────────────────────────

def customer_value(days_back=90):
    """客户价值分析

    返回:
        dict: {countries, avg_order, top_products, ltv_estimate}
    """
    since = (datetime.now() - timedelta(days=days_back)).isoformat()

    # 国家分布
    countries = _query(
        "SELECT country, COUNT(*) as c FROM customers "
        "WHERE country IS NOT NULL AND country != '' AND created_at >= ? "
        "GROUP BY country ORDER BY c DESC LIMIT 10",
        (since,)
    )

    # 报价金额统计
    quotes = _query(
        "SELECT AVG(total_amount) as avg_amt, "
        "MAX(total_amount) as max_amt, "
        "COUNT(*) as count "
        "FROM quotes WHERE created_at >= ?",
        (since,)
    )

    # 各状态客户平均评分
    state_scores = _query(
        "SELECT lead_state, AVG(lead_score) as avg_score, COUNT(*) as count "
        "FROM customers WHERE lead_score IS NOT NULL "
        "GROUP BY lead_state ORDER BY avg_score DESC"
    )

    return {
        "period_days": days_back,
        "top_countries": [{"country": r["country"], "count": r["c"]} for r in countries],
        "quotes": {
            "total": quotes[0]["count"] if quotes else 0,
            "avg_amount": round(quotes[0]["avg_amt"], 2) if quotes and quotes[0]["avg_amt"] else 0,
            "max_amount": round(quotes[0]["max_amt"], 2) if quotes and quotes[0]["max_amt"] else 0,
        },
        "state_scores": [
            {"state": r["lead_state"], "avg_score": round(r["avg_score"], 1), "count": r["count"]}
            for r in state_scores
        ],
    }


# ── 4. 汇总仪表盘 ───────────────────────────────────────

def dashboard(days_back=30):
    """一键获取所有关键指标"""
    return {
        "funnel": funnel_conversion(days_back),
        "ai": ai_efficiency(min(days_back, 30)),  # AI效率看30天
        "value": customer_value(days_back),
        "generated_at": datetime.now().isoformat(),
    }
