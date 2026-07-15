"""V2.0 Autonomous Strategy Loop — 每日自动优化闭环

每日自动运行分析:
  1. 哪些客户最赚钱          → 利润排行
  2. 哪些话术转化最高         → 话术效果分析（复用 RevenueFeedbackLoop）
  3. 哪个国家 ROI 最高        → 国家效益分析
  4. 哪个产品最赚钱           → 产品利润排行

输出:
  { focus_product, focus_region, followup_speed, discount_policy }

复用:
  - RevenueFeedbackLoop (V7 revenue_feedback_loop.py)
  - v3_conversions 表
  - dashboard_engine 的历史数据

约束:
  - 纯 SQL + 数学计算
  - 默认 dry_run=True
"""
import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")
logger = logging.getLogger("v2_strategy_loop")

# ── 优化阈值 ──────────────────────────────────────────────

FOLLOWUP_SPEED_THRESHOLDS = {
    "fast": 2,       # < 2小时回复 → 快速跟进
    "normal": 12,    # 2-12小时 → 正常
    "slow": 48,      # 12-48小时 → 慢
    "neglect": 999,  # > 48小时 → 忽略
}

DISCOUNT_POLICY_THRESHOLDS = {
    "aggressive": 0.20,    # 利润率低于20% → 不主动降价
    "normal": 0.35,        # 20-35% → 可小幅度折扣
    "conservative": 0.50,  # 35-50% → 标准折扣
    "premium": 1.0,        # >50% → 可大幅度折扣
}


def _read_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


class StrategyLoop:
    """每日自动优化策略循环"""

    @staticmethod
    def analyze_most_profitable_customers(limit=10):
        """哪些客户最赚钱

        从 orders 表分析利润排行
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT o.customer_id, c.name, c.country,
                       COUNT(o.id) as order_count,
                       SUM(o.total_amount) as total_revenue,
                       SUM(o.total_amount) * 0.45 as estimated_profit,
                       MAX(o.created_at) as last_order
                FROM orders o
                JOIN customers c ON o.customer_id = c.id
                WHERE o.status IN ('shipped', 'delivered', 'completed')
                GROUP BY o.customer_id
                ORDER BY estimated_profit DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"profitable_customers query error: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def analyze_country_roi():
        """哪个国家 ROI 最高

        按国家聚合: 总营收 / 客户数 = 人均价值
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT c.country,
                       COUNT(DISTINCT c.id) as customer_count,
                       COUNT(DISTINCT o.id) as order_count,
                       COALESCE(SUM(o.total_amount), 0) as total_revenue,
                       CASE WHEN COUNT(DISTINCT c.id) > 0
                           THEN SUM(o.total_amount) / COUNT(DISTINCT c.id)
                           ELSE 0 END as revenue_per_customer
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                    AND o.status IN ('shipped', 'delivered', 'completed')
                WHERE c.country != '' AND c.country IS NOT NULL
                GROUP BY c.country
                HAVING customer_count >= 2
                ORDER BY revenue_per_customer DESC
            """).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"country_roi query error: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def analyze_most_profitable_products():
        """哪个产品最赚钱

        从 orders.items JSON 分析产品利润
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT o.items, o.total_amount, o.status
                FROM orders o
                WHERE o.status IN ('shipped', 'delivered', 'completed')
                  AND o.items != '[]' AND o.items IS NOT NULL
                ORDER BY o.created_at DESC
                LIMIT 100
            """).fetchall()
        except Exception as e:
            logger.warning(f"product_analysis query error: {e}")
            return []
        finally:
            conn.close()

        # 解析 items JSON 统计产品类别
        product_stats = {}
        for r in rows:
            try:
                items = json.loads(r["items"])
                if isinstance(items, list):
                    for item in items:
                        name = item.get("name", item.get("product", "unknown"))
                        qty = item.get("quantity", item.get("qty", 1)) or 1
                        price = item.get("price", item.get("unit_price", 0)) or 0
                        if name not in product_stats:
                            product_stats[name] = {"count": 0, "total_revenue": 0, "orders": 0}
                        product_stats[name]["count"] += qty
                        product_stats[name]["total_revenue"] += price * qty
                        product_stats[name]["orders"] += 1
            except (json.JSONDecodeError, TypeError):
                continue

        # 排序
        sorted_products = sorted(
            product_stats.items(),
            key=lambda x: x[1]["total_revenue"],
            reverse=True
        )
        return [
            {
                "product": name,
                "units_sold": stats["count"],
                "total_revenue": round(stats["total_revenue"], 2),
                "order_count": stats["orders"],
            }
            for name, stats in sorted_products[:10]
        ]

    @staticmethod
    def analyze_followup_speed():
        """跟进速度分析

        从 messages 表分析回复延迟
        """
        conn = _read_db()
        try:
            rows = conn.execute("""
                SELECT m1.customer_id, c.name,
                       MIN(julianday(m1.created_at) - julianday(m2.created_at)) * 24 as min_gap_hours,
                       AVG(julianday(m1.created_at) - julianday(m2.created_at)) * 24 as avg_gap_hours
                FROM messages m1
                JOIN messages m2 ON m1.customer_id = m2.customer_id
                    AND m1.id > m2.id
                JOIN customers c ON m1.customer_id = c.id
                WHERE m1.direction = 'sent'
                  AND m2.direction = 'received'
                GROUP BY m1.customer_id
                HAVING avg_gap_hours IS NOT NULL
                ORDER BY avg_gap_hours
                LIMIT 20
            """).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"followup_speed query error: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def run_daily_analysis(dry_run=True):
        """运行每日策略分析

        参数:
            dry_run: True=仅分析不执行

        返回:
            dict: {
                focus_product: str,
                focus_region: str,
                followup_speed: str,
                discount_policy: str,
                analysis_date: str,
                details: { ... }
            }
        """
        logger.info(f"Running daily strategy analysis (dry_run={dry_run})")

        # 1. 利润客户排行
        top_customers = StrategyLoop.analyze_most_profitable_customers(5)
        # 2. 国家 ROI
        country_roi = StrategyLoop.analyze_country_roi()
        # 3. 产品利润排行
        top_products = StrategyLoop.analyze_most_profitable_products()
        # 4. 跟进速度
        followup_data = StrategyLoop.analyze_followup_speed()

        # ── 策略推导 ──────────────────────────────────────

        # Focus Product: 销量最高的产品
        focus_product = top_products[0]["product"] if top_products else "LED Sign"

        # Focus Region: ROI 最高的国家区域
        if country_roi:
            top_country = country_roi[0]
            focus_region = f"{top_country['country']} (${top_country['revenue_per_customer']:.0f}/客户)"
        else:
            focus_region = "US"

        # Followup Speed: 平均回复延迟
        if followup_data:
            avg_gaps = [r.get("avg_gap_hours", 0) or 0 for r in followup_data]
            overall_avg = sum(avg_gaps) / len(avg_gaps) if avg_gaps else 0
            if overall_avg <= FOLLOWUP_SPEED_THRESHOLDS["fast"]:
                followup_speed = "fast"
            elif overall_avg <= FOLLOWUP_SPEED_THRESHOLDS["normal"]:
                followup_speed = "normal"
            elif overall_avg <= FOLLOWUP_SPEED_THRESHOLDS["slow"]:
                followup_speed = "slow"
            else:
                followup_speed = "neglect"
        else:
            followup_speed = "normal"

        # Discount Policy: 基于平均利润率
        if top_customers:
            avg_margin = sum(
                (r.get("estimated_profit", 0) or 0) /
                max(r.get("total_revenue", 1) or 1, 1)
                for r in top_customers
            ) / len(top_customers)
            if avg_margin >= DISCOUNT_POLICY_THRESHOLDS["premium"]:
                discount_policy = "premium"
            elif avg_margin >= DISCOUNT_POLICY_THRESHOLDS["conservative"]:
                discount_policy = "conservative"
            elif avg_margin >= DISCOUNT_POLICY_THRESHOLDS["normal"]:
                discount_policy = "normal"
            else:
                discount_policy = "aggressive"
        else:
            discount_policy = "normal"

        # ── 尝试调用 RevenueFeedbackLoop ──────────────────

        feedback_insights = {}
        try:
            from ai_engine.revenue_feedback_loop import RevenueFeedbackLoop
            loop = RevenueFeedbackLoop()
            feedback_insights = loop.get_insights(days=30)
        except Exception as e:
            logger.warning(f"RevenueFeedbackLoop unavailable: {e}")

        result = {
            "focus_product": focus_product,
            "focus_region": focus_region,
            "followup_speed": followup_speed,
            "discount_policy": discount_policy,
            "analysis_date": datetime.now().isoformat(),
            "details": {
                "top_customers": top_customers,
                "country_roi": country_roi[:5] if country_roi else [],
                "top_products": top_products,
                "followup_avg_hours": round(overall_avg, 2) if followup_data else None,
                "feedback_insights": feedback_insights,
            },
            "dry_run": dry_run,
        }

        if not dry_run:
            logger.info(
                f"Strategy: product={focus_product} region={focus_region} "
                f"followup={followup_speed} discount={discount_policy}"
            )

        return result

    @staticmethod
    def get_strategy_recommendations(strategy_result):
        """将策略分析结果转为可执行建议"""
        recs = []
        s = strategy_result.get("details", {})

        # 跟进速度建议
        speed = strategy_result.get("followup_speed", "normal")
        speed_advice = {
            "fast": "跟进速度良好，保持",
            "normal": "正常跟进速度，可考虑自动化加速",
            "slow": "跟进偏慢，建议设置自动提醒或缩短检查间隔",
            "neglect": "跟进严重滞后，需要立即优化流程",
        }
        recs.append(f"跟进策略: {speed_advice.get(speed, '')}")

        # 折扣策略建议
        dp = strategy_result.get("discount_policy", "normal")
        dp_advice = {
            "premium": "利润空间充足，可适当给予折扣促成快速成交",
            "conservative": "利润良好，标准折扣权限即可",
            "normal": "利润一般，控制折扣在10%以内",
            "aggressive": "利润偏低，不建议主动降价",
        }
        recs.append(f"折扣策略: {dp_advice.get(dp, '')}")

        # 重点产品建议
        recs.append(f"重点产品: {strategy_result.get('focus_product')}")

        # 重点市场建议
        recs.append(f"重点市场: {strategy_result.get('focus_region')}")

        return recs
