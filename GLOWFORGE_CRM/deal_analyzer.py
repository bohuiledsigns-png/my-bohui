"""V3 Deal Analyzer — 成交复盘引擎

成交/失败后自动分析原因（关键词匹配），生成洞察和建议。

功能:
  - analyze_conversation(): 对单条对话做关键字匹配分析
  - analyze_batch(): 批量分析最近成交/失败的对话
  - generate_recommendations(): 基于累积数据生成可执行建议
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import get_db
from conversion_tracker import ConversionTracker


class DealAnalyzer:
    """成交复盘引擎"""

    # 成交成功因素关键词
    WINNING_FACTOR_KEYWORDS = {
        "A/B/C B version": ["b version", "standard款", "热销款", "most popular", "most clients choose"],
        "emphasized durability": ["durability", "long-lasting", "10年", "使用寿命", "多年使用", "years"],
        "used urgency trigger": ["production slot", "this week", "limited", "紧迫", "尽快", "today", "now"],
        "price anchor effective": ["anchor", "most clients choose", "价格锚", "通常选择", "most popular"],
        "social proof used": ["case study", "similar project", "案例", "similar client", "客户反馈", " installed"],
        "risk framing worked": ["risk", "褪色", "更换成本", "maintenance cost", "low price", "cheap"],
        "visual effect pitch": ["foot traffic", "客流量", "visibility", "可见度", "醒目", "attract"],
        "factory expertise": ["certification", "factory", "生产线", "professional", "ISO", "CE"],
    }

    # 失败原因关键词
    LOST_REASON_KEYWORDS = {
        "price sensitive": ["too expensive", "over budget", "太贵", "超出预算", "cost too much", "pricey"],
        "no case study shown": ["unproven", "no reference", "没有案例", "cannot show", "no proof"],
        "competitor better": ["competitor", "other supplier", "别家", "别处", "cheaper elsewhere", "better offer"],
        "response too slow": ["already ordered", "late reply", "already placed", "too late", "found another"],
        "missing certification": ["certification", "certificate", "认证", "资质", "no proof"],
        "communication issue": ["language barrier", "misunderstanding", "误解", "didn't understand", "confused"],
    }

    def __init__(self):
        self._tracker = ConversionTracker()

    # ==================== 单条分析 ====================

    def analyze_conversation(self, conversion_id, messages=None, state_path=None, reply_texts=None):
        """分析单条已完成对话

        Args:
            conversion_id: v3_conversions id
            messages: 对话消息列表（可选）
            state_path: 状态路径（可选）
            reply_texts: AI 回复文本列表（可选）

        Returns:
            dict: {winning_factors, lost_reasons, key_insight, result}
        """
        conn = get_db()
        row = conn.execute("SELECT * FROM v3_conversions WHERE id=?", (conversion_id,)).fetchone()
        conn.close()

        if not row:
            return {"error": "conversion not found"}

        conv = dict(row)
        result = conv.get("final_result", "open")
        texts_to_analyze = " ".join(reply_texts or [conv.get("quote_sent") or ""])
        state_path_str = " ".join(
            json.loads(conv.get("state_path", "[]")) if isinstance(conv.get("state_path"), str)
            else conv.get("state_path") or []
        )

        corpus = (texts_to_analyze + " " + state_path_str).lower()

        winning_factors = []
        lost_reasons = []

        if result == "won":
            for factor, keywords in self.WINNING_FACTOR_KEYWORDS.items():
                for kw in keywords:
                    if kw.lower() in corpus:
                        winning_factors.append(factor)
                        break

        if result == "lost":
            for reason, keywords in self.LOST_REASON_KEYWORDS.items():
                for kw in keywords:
                    if kw.lower() in corpus:
                        lost_reasons.append(reason)
                        break

        # 生成关键洞察
        insight = self._generate_insight(result, winning_factors, lost_reasons, conv)

        # 保存分析结果
        analysis = {
            "winning_factors": winning_factors,
            "lost_reasons": lost_reasons,
            "key_insight": insight,
            "result": result,
        }

        if result in ("won", "lost"):
            self.save_analysis(conversion_id, conv.get("customer_id", 0), result, winning_factors, lost_reasons, insight)

        return analysis

    # ==================== 批量分析 ====================

    def analyze_batch(self, days=30):
        """批量分析最近已关闭的对话

        Returns:
            dict: {top_winning_factors, top_lost_reasons, recommendations}
        """
        conversions = self._tracker.get_conversions_for_training(days=days, min_records=0)
        if not conversions:
            return {"top_winning_factors": [], "top_lost_reasons": [], "recommendations": []}

        factor_counts = {}
        reason_counts = {}
        won_total = 0
        lost_total = 0

        for conv in conversions:
            result = conv.get("final_result")
            if result == "won":
                won_total += 1
                analysis = self.analyze_conversation(conv["id"])
                for f in analysis.get("winning_factors", []):
                    factor_counts[f] = factor_counts.get(f, 0) + 1
            elif result == "lost":
                lost_total += 1
                analysis = self.analyze_conversation(conv["id"])
                for r in analysis.get("lost_reasons", []):
                    reason_counts[r] = reason_counts.get(r, 0) + 1

        top_factors = sorted(
            [{"factor": k, "count": v, "rate": round(v / won_total, 2) if won_total else 0}
             for k, v in factor_counts.items()],
            key=lambda x: x["count"], reverse=True
        )[:10]

        top_reasons = sorted(
            [{"reason": k, "count": v, "rate": round(v / lost_total, 2) if lost_total else 0}
             for k, v in reason_counts.items()],
            key=lambda x: x["count"], reverse=True
        )[:10]

        recommendations = self._generate_recommendations_from_data(
            factor_counts, reason_counts, won_total, lost_total
        )

        return {
            "total_analyzed": len(conversions),
            "won": won_total,
            "lost": lost_total,
            "top_winning_factors": top_factors,
            "top_lost_reasons": top_reasons,
            "recommendations": recommendations,
        }

    # ==================== 保存 ====================

    def save_analysis(self, conversion_id, customer_id, result, winning_factors, lost_reasons, insight=""):
        """保存分析结果到数据库"""
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM v3_deal_analyses WHERE conversion_id=?", (conversion_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE v3_deal_analyses SET
                   winning_factors=?, lost_reasons=?, key_insight=?, analyzed_at=CURRENT_TIMESTAMP
                   WHERE conversion_id=?""",
                (json.dumps(winning_factors, ensure_ascii=False),
                 json.dumps(lost_reasons, ensure_ascii=False),
                 insight, conversion_id)
            )
        else:
            conn.execute(
                """INSERT INTO v3_deal_analyses
                   (conversion_id, customer_id, result, winning_factors, lost_reasons, key_insight)
                   VALUES (?,?,?,?,?,?)""",
                (conversion_id, customer_id, result,
                 json.dumps(winning_factors, ensure_ascii=False),
                 json.dumps(lost_reasons, ensure_ascii=False), insight)
            )
        conn.commit()
        conn.close()

    # ==================== 洞察和建议 ====================

    def get_insights(self, days=90):
        """获取聚合洞察"""
        conn = get_db()
        rows = conn.execute(
            """SELECT result, winning_factors, lost_reasons, key_insight
               FROM v3_deal_analyses
               WHERE analyzed_at >= datetime('now', '-' || ? || ' days')
               ORDER BY analyzed_at DESC""", (str(days),)
        ).fetchall()
        conn.close()

        factors = {}
        reasons = {}
        for r in rows:
            wf = json.loads(r["winning_factors"]) if isinstance(r["winning_factors"], str) else r["winning_factors"]
            lr = json.loads(r["lost_reasons"]) if isinstance(r["lost_reasons"], str) else r["lost_reasons"]
            for f in (wf or []):
                factors[f] = factors.get(f, 0) + 1
            for rr in (lr or []):
                reasons[rr] = reasons.get(rr, 0) + 1

        return {
            "total_analyses": len(rows),
            "winning_factors": sorted(factors.items(), key=lambda x: x[1], reverse=True),
            "lost_reasons": sorted(reasons.items(), key=lambda x: x[1], reverse=True),
        }

    def generate_recommendations(self):
        """基于累积数据生成可执行的建议"""
        batch = self.analyze_batch(days=60)
        recs = batch.get("recommendations", [])

        # 如果没有足够数据，返回通用建议
        if not recs:
            recs = [
                "Continue collecting conversion data — at least 20 closed deals needed for meaningful analysis.",
                "Use A/B version B (visual effect + foot traffic) as default for BUDGET and NEEDS_ANALYSIS states.",
                "Always include urgency trigger (production slot, limited availability) in FINAL state replies.",
            ]

        return recs

    # ==================== 内部方法 ====================

    def _generate_insight(self, result, winning_factors, lost_reasons, conv):
        """生成单条分析的关键洞察"""
        parts = []
        if result == "won" and winning_factors:
            parts.append(f"Won with: {', '.join(winning_factors[:3])}")
        if result == "lost" and lost_reasons:
            parts.append(f"Lost due to: {', '.join(lost_reasons[:3])}")
        if conv.get("state_path"):
            try:
                path = json.loads(conv["state_path"]) if isinstance(conv["state_path"], str) else conv["state_path"]
                if isinstance(path, list) and len(path) > 1:
                    parts.append(f"Path: {'→'.join(path)}")
            except Exception:
                pass
        if conv.get("messages_count"):
            parts.append(f"{conv['messages_count']} msgs")
        return "; ".join(parts) if parts else "Insufficient data for insight"

    def _generate_recommendations_from_data(self, factor_counts, reason_counts, won_total, lost_total):
        """基于聚合数据生成可执行建议"""
        recs = []
        total = won_total + lost_total

        # 找出最强的成功因素
        if factor_counts:
            top_factor = max(factor_counts, key=factor_counts.get)
            if factor_counts[top_factor] >= 3:
                recs.append(
                    f"'{top_factor}' appears in {factor_counts[top_factor]}/{won_total} won deals. "
                    f"Consider making this the default approach for all states."
                )

        # 找出最常见的失败原因
        if reason_counts:
            top_reason = max(reason_counts, key=reason_counts.get)
            if reason_counts[top_reason] >= 3:
                recs.append(
                    f"'{top_reason}' is the top lost reason ({reason_counts[top_reason]}/{lost_total} lost). "
                    f"Review sales script to address this proactively."
                )

        # 通用建议
        if won_total > 0:
            recs.append(
                f"Win rate: {won_total}/{total} ({round(won_total/total*100, 1)}%). "
                f"{'Above average' if won_total/total > 0.4 else 'Room for improvement'}."
            )

        return recs


# ==================== 快捷入口 ====================

analyzer = DealAnalyzer()


def analyze_deal(conversion_id):
    return analyzer.analyze_conversation(conversion_id)
