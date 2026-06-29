"""Geo Analyzer — 地区深度分析

对目标市场进行地域聚类分析，提供区域级洞察和市场进入策略。
"""
import logging

from strategy_engine.db import _read_db, normalize_country

logger = logging.getLogger("geo_analyzer")

REGION_CLUSTERS = {
    "NA": {"name": "North America", "countries": ["US", "CA"]},
    "EU": {"name": "Europe", "countries": ["GB", "DE", "FR", "IT", "ES", "NL"]},
    "MEA": {"name": "Middle East & Africa", "countries": ["AE", "SA", "QA", "KW", "OM", "BH"]},
    "APAC": {"name": "Asia Pacific", "countries": ["AU", "SG", "JP", "MY"]},
    "LATAM": {"name": "Latin America", "countries": []},
}


class GeoAnalyzer:
    """地区深度分析引擎"""

    @staticmethod
    def analyze_country(country_code):
        """深度分析单个国家市场"""
        conn = _read_db()
        try:
            cust = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN created_at >= datetime('now', '-90 days') THEN 1 ELSE 0 END) as new_90d
                FROM customers WHERE country = ?
            """, (country_code,)).fetchone()

            orders = conn.execute("""
                SELECT COUNT(*) as total,
                       COALESCE(SUM(total_amount), 0) as revenue,
                       COALESCE(AVG(total_amount), 0) as aov,
                       COUNT(DISTINCT customer_id) as buying_customers
                FROM orders
                WHERE customer_id IN (
                    SELECT id FROM customers WHERE country = ?
                ) AND status IN ('shipped', 'delivered', 'completed')
            """, (country_code,)).fetchone()

            conv = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN final_result='won' THEN 1 ELSE 0 END) as won
                FROM v3_conversions v
                JOIN customers c ON c.id = v.customer_id
                WHERE c.country = ? AND v.final_result IN ('won', 'lost')
            """, (country_code,)).fetchone()

        except Exception as e:
            logger.warning(f"Country analysis error: {e}")
            return {}
        finally:
            conn.close()

        conv_rate = (conv["won"] / conv["total"] * 100
                     if conv and conv["total"] > 0 else 0)

        return {
            "country_code": country_code,
            "region": MarketRegionMapper.get_region(country_code),
            "customers": {
                "total": cust["total"] if cust else 0,
                "new_90d": cust["new_90d"] if cust else 0,
            },
            "orders": {
                "total": orders["total"] if orders else 0,
                "revenue": round(orders["revenue"], 2) if orders else 0,
                "avg_order_value": round(orders["aov"], 2) if orders else 0,
                "buying_customers": orders["buying_customers"] if orders else 0,
            },
            "conversion": {
                "rate": round(conv_rate, 2),
                "total_opportunities": conv["total"] if conv else 0,
                "won": conv["won"] if conv else 0,
            },
        }

    @staticmethod
    def analyze_region(region_key):
        """分析整个区域的综合表现"""
        countries = REGION_CLUSTERS.get(region_key, {}).get("countries", [])
        if not countries:
            return {"region": region_key, "error": "No countries in region"}

        results = []
        for cc in countries:
            results.append(GeoAnalyzer.analyze_country(cc))

        total_revenue = sum(r.get("orders", {}).get("revenue", 0) for r in results)
        total_customers = sum(r.get("customers", {}).get("total", 0) for r in results)
        total_orders = sum(r.get("orders", {}).get("total", 0) for r in results)

        return {
            "region_key": region_key,
            "region_name": REGION_CLUSTERS[region_key]["name"],
            "countries": results,
            "aggregates": {
                "total_revenue": round(total_revenue, 2),
                "total_customers": total_customers,
                "total_orders": total_orders,
                "avg_aov": round(total_revenue / total_orders, 2) if total_orders > 0 else 0,
            },
        }

    @staticmethod
    def compare_countries(country_codes):
        """横向比较多个国家"""
        return [GeoAnalyzer.analyze_country(cc) for cc in country_codes]

    @staticmethod
    def get_entry_strategy(country_code):
        """生成市场进入策略建议"""
        analysis = GeoAnalyzer.analyze_country(country_code)
        if not analysis:
            return {"country": country_code, "recommendation": "insufficient_data"}

        customers = analysis.get("customers", {})
        orders = analysis.get("orders", {})
        conversion = analysis.get("conversion", {})

        if customers.get("total", 0) == 0:
            return {
                "country": country_code,
                "phase": "explore",
                "action": "cold_entry",
                "description": "新市场，建议先通过V2主动营销试探需求",
            }
        elif orders.get("total", 0) < 5:
            return {
                "country": country_code,
                "phase": "test",
                "action": "targeted_outreach",
                "description": "有客户基础但成交少，建议定向推广主打产品",
            }
        elif conversion.get("rate", 0) > 30:
            return {
                "country": country_code,
                "phase": "scale",
                "action": "aggressive_expand",
                "description": "高转化市场，建议加大投入扩大份额",
            }
        else:
            return {
                "country": country_code,
                "phase": "optimize",
                "action": "conversion_optimization",
                "description": "有基础成交但转化偏低，建议优化话术和定价",
            }


class MarketRegionMapper:
    """市场-区域映射工具"""

    _MAP = {
        "US": "NA", "CA": "NA",
        "GB": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU", "NL": "EU",
        "AE": "MEA", "SA": "MEA", "QA": "MEA", "KW": "MEA", "OM": "MEA", "BH": "MEA",
        "AU": "APAC", "SG": "APAC", "JP": "APAC", "MY": "APAC",
    }

    @staticmethod
    def get_region(country_code):
        cc = normalize_country(country_code)
        return MarketRegionMapper._MAP.get(cc, "OTHER")

    @staticmethod
    def get_countries_by_region(region):
        return [cc for cc, r in MarketRegionMapper._MAP.items() if r == region]
