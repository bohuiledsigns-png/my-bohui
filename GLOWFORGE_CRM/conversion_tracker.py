"""V3 Conversion Tracker — 成交追踪器

记录每次对话的完整生命周期，为 A/B 优化器、价格优化器、意图权重调优器提供数据基础。

每条消息处理完成后记录一条 v3_conversions 记录，deal 关闭时更新结果。
"""
import json
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db, init_v3_tables


class ConversionTracker:
    """成交追踪器 — 记录和查询对话成交数据"""

    def __init__(self):
        # 确保表已存在
        try:
            init_v3_tables()
        except Exception:
            pass

    # ==================== 写入 ====================

    def record_conversation(self, customer_id, state_info=None, behavior=None,
                            intent="", ab_version="", quote_amount=0):
        """记录一条新对话到 v3_conversions

        Args:
            customer_id: 客户 ID
            state_info: detect_sales_state() 的 dict 输出
            behavior: SalesExecutor.execute() 的 dict 输出
            intent: 检测到的意图
            ab_version: A/B/C 版本
            quote_amount: 报价金额

        Returns:
            int: conversion_id
        """
        if state_info is None:
            state_info = {}
        if behavior is None:
            behavior = {}

        state = state_info.get("state", "NEW")
        price_tier = state_info.get("price_tier", "UNKNOWN")
        country = state_info.get("country", "")
        deal_prob = state_info.get("deal_probability", 0)
        conv_score = behavior.get("conversion_score", 0)

        conn = get_db()
        cur = conn.execute(
            """INSERT INTO v3_conversions
               (customer_id, country, intent, initial_state, final_state, state_path,
                price_tier, ab_version, quote_amount, conversion_score, deal_probability)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (customer_id, country, intent, state, state, json.dumps([state], ensure_ascii=False),
             price_tier, ab_version, quote_amount, conv_score, deal_prob)
        )
        conv_id = cur.lastrowid
        conn.commit()
        conn.close()
        return conv_id

    def close_conversation(self, conversion_id, final_result="won", revenue=0,
                           profit=0, lost_reason=""):
        """关闭一条对话记录（成交/失败）

        Args:
            conversion_id: v3_conversions id
            final_result: 'won' | 'lost'
            revenue: 成交金额
            profit: 利润
            lost_reason: 失败原因
        """
        conn = get_db()
        conn.execute(
            """UPDATE v3_conversions SET
               final_result=?, revenue=?, profit=?, lost_reason=?,
               closed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (final_result, revenue, profit, lost_reason, conversion_id)
        )
        conn.commit()
        conn.close()

    def update_state_path(self, conversion_id, new_state):
        """追加新状态到 state_path JSON 数组"""
        conn = get_db()
        row = conn.execute(
            "SELECT state_path, messages_count FROM v3_conversions WHERE id=?",
            (conversion_id,)
        ).fetchone()
        if not row:
            conn.close()
            return
        path = json.loads(row["state_path"]) if isinstance(row["state_path"], str) else row["state_path"] or []
        if isinstance(path, list):
            path.append(new_state)
        count = (row["messages_count"] or 0) + 1
        conn.execute(
            "UPDATE v3_conversions SET state_path=?, messages_count=?, final_state=? WHERE id=?",
            (json.dumps(path, ensure_ascii=False), count, new_state, conversion_id)
        )
        conn.commit()
        conn.close()

    # ==================== 查询 ====================

    def get_conversions(self, state=None, result=None, days=None, limit=50):
        """查询转换记录"""
        conn = get_db()
        sql = "SELECT * FROM v3_conversions WHERE 1=1"
        params = []
        if state:
            sql += " AND (initial_state=? OR final_state=?)"
            params.extend([state, state])
        if result:
            sql += " AND final_result=?"
            params.append(result)
        if days:
            sql += " AND created_at >= datetime('now', '-' || ? || ' days')"
            params.append(str(days))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_conversion_rate(self, filters=None):
        """获取聚合成交率"""
        conn = get_db()
        filters = filters or {}
        sql = "SELECT final_result, COUNT(*) as cnt FROM v3_conversions WHERE final_result != 'open'"
        params = []
        if filters.get("state"):
            sql += " AND (initial_state=? OR final_state=?)"
            params.extend([filters["state"], filters["state"]])
        if filters.get("intent"):
            sql += " AND intent=?"
            params.append(filters["intent"])
        if filters.get("price_tier"):
            sql += " AND price_tier=?"
            params.append(filters["price_tier"])
        if filters.get("ab_version"):
            sql += " AND ab_version=?"
            params.append(filters["ab_version"])
        if filters.get("days"):
            sql += " AND created_at >= datetime('now', '-' || ? || ' days')"
            params.append(str(filters["days"]))
        sql += " GROUP BY final_result"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        stats = {"total": 0, "won": 0, "lost": 0, "silent": 0, "rate": 0.0}
        for r in rows:
            d = dict(r)
            stats[d["final_result"]] = d["cnt"]
            stats["total"] += d["cnt"]
        if stats["total"] > 0:
            stats["rate"] = round(stats["won"] / stats["total"], 4)
        return stats

    def get_conversions_for_training(self, days=30, min_records=20):
        """获取用于优化的已关闭转换记录"""
        conn = get_db()
        rows = conn.execute(
            """SELECT * FROM v3_conversions
               WHERE final_result IN ('won','lost')
               AND created_at >= datetime('now', '-' || ? || ' days')
               ORDER BY id DESC""", (str(days),)
        ).fetchall()
        conn.close()
        results = [dict(r) for r in rows]
        if len(results) < min_records:
            return []
        return results

    # ==================== 优化器专用查询 ====================

    def get_ab_performance(self, state=None, days=30):
        """获取 A/B 版本性能数据（按状态 + 版本聚合）"""
        conn = get_db()
        sql = """SELECT
                   COALESCE(initial_state, 'UNKNOWN') as state,
                   ab_version,
                   COUNT(*) as total_trials,
                   SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won_count,
                   SUM(CASE WHEN final_result='lost' THEN 1 ELSE 0 END) as lost_count,
                   AVG(conversion_score) as avg_score
                 FROM v3_conversions
                 WHERE ab_version IN ('A','B','C')
                 AND created_at >= datetime('now', '-' || ? || ' days')
              """
        params = [str(days)]
        if state:
            sql += " AND (initial_state=? OR final_state=?)"
            params.extend([state, state])
        sql += " GROUP BY state, ab_version ORDER BY state, ab_version"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["conversion_rate"] = round(d["won_count"] / d["total_trials"], 4) if d["total_trials"] > 0 else 0
            d["avg_score"] = round(d["avg_score"] or 0, 1)
            results.append(d)
        return results

    def get_price_performance(self, price_tier=None, days=90):
        """获取各价格点成交性能"""
        conn = get_db()
        sql = """SELECT
                   price_tier,
                   COALESCE(quote_sent, '') as price_range,
                   COUNT(*) as total_trials,
                   SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won_count,
                   AVG(CASE WHEN final_result='won' THEN revenue ELSE NULL END) as avg_revenue
                 FROM v3_conversions
                 WHERE final_result != 'open'
                 AND created_at >= datetime('now', '-' || ? || ' days')
              """
        params = [str(days)]
        if price_tier:
            sql += " AND price_tier=?"
            params.append(price_tier)
        sql += " GROUP BY price_tier, price_range ORDER BY price_tier, total_trials DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["conversion_rate"] = round(d["won_count"] / d["total_trials"], 4) if d["total_trials"] > 0 else 0
            d["avg_revenue"] = round(d["avg_revenue"] or 0, 2)
            results.append(d)
        return results

    def get_intent_performance(self, days=60):
        """获取意图→成交统计数据"""
        conn = get_db()
        rows = conn.execute(
            """SELECT
                 intent,
                 COUNT(*) as total_occurrences,
                 SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won_count,
                 SUM(CASE WHEN final_result='lost' THEN 1 ELSE 0 END) as lost_count
               FROM v3_conversions
               WHERE intent != '' AND intent != 'unknown'
               AND final_result != 'open'
               AND created_at >= datetime('now', '-' || ? || ' days')
               GROUP BY intent
               ORDER BY total_occurrences DESC""", (str(days),)
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["conversion_rate"] = round(d["won_count"] / d["total_occurrences"], 4) if d["total_occurrences"] > 0 else 0
            results.append(d)
        return results


# ==================== 快捷入口 ====================

tracker = ConversionTracker()


def record_conversation(**kwargs):
    return tracker.record_conversation(**kwargs)


def close_conversation(**kwargs):
    return tracker.close_conversation(**kwargs)
