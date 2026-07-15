"""Dashboard Engine — 收入仪表盘

实时业务 KPI 汇总：线索数、转化率、平均利润、国家/行业分布、活动表现。
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class DashboardEngine:
    """收入仪表盘引擎"""

    def get_kpi_summary(self) -> dict:
        """获取核心KPI汇总

        Returns:
            dict: {
                leads_today, leads_week, leads_month,
                conversion_rate, avg_margin, total_revenue,
                active_leads, delayed_leads, lost_leads
            }
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db
        except ImportError:
            return self._get_kpi_direct()

        conn = get_db()

        # 今日线索
        today = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE date(created_at)=date('now')"
        ).fetchone()[0]

        # 本周线索
        week = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]

        # 本月线索
        month = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE created_at >= datetime('now', '-30 days')"
        ).fetchone()[0]

        # 各状态数量
        status_counts = dict(conn.execute(
            "SELECT lead_status, COUNT(*) FROM customers WHERE lead_status IS NOT NULL AND lead_status != '' GROUP BY lead_status"
        ).fetchall())

        # 转化率 (有回复的 / 已触达的)
        contacted = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE lead_status IN ('contacted', 'qualified', 'negotiating', 'hot', 'customer')"
        ).fetchone()[0]
        converted = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE lead_status='customer'"
        ).fetchone()[0]
        conv_rate = round(converted / contacted * 100, 1) if contacted > 0 else 0

        # 总收入
        revenue = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status NOT IN ('cancelled', 'lost')"
        ).fetchone()[0]

        conn.close()

        return {
            "leads_today": today,
            "leads_week": week,
            "leads_month": month,
            "new_leads": status_counts.get("new", 0),
            "contacted": status_counts.get("contacted", 0),
            "negotiating": status_counts.get("negotiating", 0),
            "customers": status_counts.get("customer", 0),
            "lost": status_counts.get("lost", 0),
            "cold": status_counts.get("cold", 0),
            "conversion_rate": conv_rate,
            "total_revenue": float(revenue),
            "total_leads": sum(status_counts.values()),
        }

    def get_conversion_funnel(self) -> dict:
        """获取转化漏斗数据

        Returns:
            dict: {stage, count, percentage} for each stage
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db
        except ImportError:
            return {}

        conn = get_db()

        stages_order = ["new", "contacted", "qualified", "negotiating", "hot", "customer"]
        funnel = []
        total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

        for stage in stages_order:
            count = conn.execute(
                "SELECT COUNT(*) FROM customers WHERE lead_status=?", (stage,)
            ).fetchone()[0]
            funnel.append({
                "stage": stage,
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0,
            })

        conn.close()

        # 流失率（从上一阶段到下一阶段）
        for i in range(1, len(funnel)):
            prev = funnel[i - 1]["count"]
            curr = funnel[i]["count"]
            funnel[i]["drop_rate"] = round(
                (1 - curr / prev) * 100, 1
            ) if prev > 0 else 0

        return {"total_leads": total, "funnel": funnel}

    def get_campaign_performance(self) -> list:
        """获取各活动表现

        Returns:
            list: [{campaign_name, total, contacted, replied, converted, revenue, conversion_rate}]
        """
        results = []

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            # 从 campaigns 表获取
            campaigns = conn.execute(
                "SELECT * FROM campaigns WHERE status='active' OR status='completed'"
            ).fetchall()

            for c in campaigns:
                total = c["total_leads"] or 0
                converted = c["converted_leads"] or 0
                results.append({
                    "campaign_name": c["name"],
                    "campaign_id": c["id"],
                    "total_leads": total,
                    "contacted": c["contacted_leads"] or 0,
                    "replied": c["replied_leads"] or 0,
                    "converted": converted,
                    "revenue": float(c["revenue_generated"] or 0),
                    "conversion_rate": round(converted / total * 100, 1) if total > 0 else 0,
                    "status": c["status"],
                })

            # 如果没有 campaigns 表或数据，从 customers 查
            if not results:
                results = self._get_campaign_from_customers(conn)

            conn.close()
        except Exception:
            try:
                results = self._get_campaign_from_customers()
            except Exception:
                results = []

        return results

    def get_top_leads(self, limit: int = 10) -> list:
        """获取最高评分线索

        Returns:
            list: [{id, name, company, country, score, status, last_contacted}]
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, name, company, country, lead_score, lead_status,
                          last_contacted_at, created_at
                   FROM customers
                   WHERE lead_score IS NOT NULL AND lead_score > 0
                   ORDER BY lead_score DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_geo_distribution(self) -> list:
        """获取国家分布统计

        Returns:
            list: [{country, count, percentage}]
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            rows = conn.execute(
                "SELECT country, COUNT(*) as count FROM customers WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY count DESC"
            ).fetchall()
            conn.close()
            return [{
                "country": r["country"],
                "count": r["count"],
                "percentage": round(r["count"] / total * 100, 1) if total > 0 else 0,
            } for r in rows]
        except Exception:
            return []

    def get_industry_distribution(self) -> list:
        """获取行业分布统计（从 notes/company 关键词推断）"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT company, notes, country FROM customers"
            ).fetchall()
            conn.close()

            industries = {}
            for r in rows:
                text = f"{r['company'] or ''} {r['notes'] or ''}".lower()
                industry = self._detect_industry(text)
                if industry:
                    industries[industry] = industries.get(industry, 0) + 1

            total = sum(industries.values()) or 1
            return [{
                "industry": ind,
                "count": cnt,
                "percentage": round(cnt / total * 100, 1),
            } for ind, cnt in sorted(industries.items(), key=lambda x: -x[1])]
        except Exception:
            return []

    def get_revenue_trend(self, days: int = 30) -> list:
        """获取收入趋势

        Returns:
            list: [{date, revenue, orders}]
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT date(created_at) as day,
                          COUNT(*) as orders,
                          COALESCE(SUM(total_amount), 0) as revenue
                   FROM orders
                   WHERE created_at >= datetime('now', ? || ' days')
                     AND status NOT IN ('cancelled', 'lost')
                   GROUP BY date(created_at)
                   ORDER BY day""",
                (f"-{days}",)
            ).fetchall()
            conn.close()
            return [{"date": r["day"], "revenue": float(r["revenue"]), "orders": r["orders"]} for r in rows]
        except Exception:
            return []

    def _get_kpi_direct(self) -> dict:
        """直接SQL查询（不依赖database.py的get_db）"""
        try:
            conn = sqlite3.connect(DB_PATH)
            today = conn.execute("SELECT COUNT(*) FROM customers WHERE date(created_at)=date('now')").fetchone()[0]
            week = conn.execute("SELECT COUNT(*) FROM customers WHERE created_at >= datetime('now', '-7 days')").fetchone()[0]
            month = conn.execute("SELECT COUNT(*) FROM customers WHERE created_at >= datetime('now', '-30 days')").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            revenue = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status NOT IN ('cancelled', 'lost')").fetchone()[0]

            contacted = conn.execute("SELECT COUNT(*) FROM customers WHERE lead_status IN ('contacted','qualified','negotiating','hot','customer')").fetchone()[0]
            converted = conn.execute("SELECT COUNT(*) FROM customers WHERE lead_status='customer'").fetchone()[0]

            conn.close()
            return {
                "leads_today": today, "leads_week": week, "leads_month": month,
                "total_leads": total, "total_revenue": float(revenue),
                "conversion_rate": round(converted / contacted * 100, 1) if contacted > 0 else 0,
                "new_leads": 0, "contacted": 0, "negotiating": 0,
                "customers": 0, "lost": 0, "cold": 0,
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_campaign_from_customers(self, conn=None) -> list:
        """从customers表的campaign字段获取活动数据"""
        try:
            close = False
            if conn is None:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                close = True

            rows = conn.execute(
                "SELECT campaign, COUNT(*) as total FROM customers WHERE campaign IS NOT NULL AND campaign != '' GROUP BY campaign"
            ).fetchall()
            results = []
            for r in rows:
                results.append({
                    "campaign_name": r["campaign"],
                    "total_leads": r["total"],
                    "contacted": 0, "replied": 0,
                    "converted": 0, "revenue": 0,
                    "conversion_rate": 0, "status": "active",
                })
            if close:
                conn.close()
            return results
        except Exception:
            return []

    def _detect_industry(self, text: str) -> str:
        """从文本检测行业"""
        keywords = {
            "restaurant": ["restaurant", "cafe", "coffee", "pizza", "grill", "bar", "pub", "food", "diner"],
            "retail": ["store", "shop", "retail", "boutique", "market", "mall"],
            "hotel": ["hotel", "inn", "resort", "hostel"],
            "office": ["office", "corp", "inc", "ltd", "professional"],
            "salon": ["salon", "spa", "beauty", "barber"],
        }
        for industry, kws in keywords.items():
            if any(kw in text for kw in kws):
                return industry
        return "other"


    # ==================== V5: 跨市场聚合 ====================

    def get_revenue_by_region(self, days: int = 30) -> list:
        """按区域聚合收入"""
        try:
            from revenue_dashboard_v5 import RevenueDashboardV5
            return RevenueDashboardV5().get_revenue_by_region(days)
        except Exception:
            return []

    def get_profit_margin_by_region(self, days: int = 30) -> list:
        """按区域聚合利润"""
        try:
            from revenue_dashboard_v5 import RevenueDashboardV5
            return RevenueDashboardV5().get_profit_margin_by_region(days)
        except Exception:
            return []

    def get_global_kpi_summary(self) -> dict:
        """全球KPI汇总"""
        try:
            from revenue_dashboard_v5 import RevenueDashboardV5
            return RevenueDashboardV5().get_global_kpi_summary()
        except Exception:
            return {}


# ==================== 测试 ====================
if __name__ == "__main__":
    d = DashboardEngine()

    print("=== KPI Summary ===")
    kpi = d.get_kpi_summary()
    for k, v in kpi.items():
        print(f"  {k}: {v}")

    print("\n=== Conversion Funnel ===")
    funnel = d.get_conversion_funnel()
    print(f"  Total leads: {funnel.get('total_leads', 0)}")
    for stage in funnel.get("funnel", []):
        print(f"  {stage['stage']}: {stage['count']} ({stage['percentage']}%)")

    print("\n=== Geo Distribution ===")
    geo = d.get_geo_distribution()
    for g in geo[:5]:
        print(f"  {g['country']}: {g['count']} ({g['percentage']}%)")

    print("\n=== Industry Distribution ===")
    ind = d.get_industry_distribution()
    for i in ind[:5]:
        print(f"  {i['industry']}: {i['count']} ({i['percentage']}%)")

    print("\n=== Top Leads ===")
    top = d.get_top_leads(5)
    for t in top:
        print(f"  {t.get('name', '?')} ({t.get('country', '?')}): score={t.get('lead_score', 'N/A')}")
