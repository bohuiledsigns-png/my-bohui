"""Region Engine — 区域引擎（V5）

全球市场区域定义、汇率管理、市场定价策略。
提供所有 V5 模块依赖的基础地理/货币/定价服务。
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class RegionEngine:
    """区域引擎 — 市场区域定义 + 汇率管理 + 市场定价"""

    REGION_DEFINITIONS = {
        "NA": {
            "name": "North America",
            "countries": ["US", "CA"],
            "base_currency": "USD",
            "default_markup": 1.4,
        },
        "EU": {
            "name": "Europe",
            "countries": ["GB", "DE", "FR", "IT", "ES", "NL", "CH", "SE", "NO", "DK", "BE", "PT"],
            "base_currency": "EUR",
            "default_markup": 1.35,
        },
        "APAC": {
            "name": "Asia Pacific",
            "countries": ["JP", "AU", "SG", "NZ", "KR", "MY", "TH", "PH", "VN", "ID", "TW", "HK"],
            "base_currency": "USD",
            "default_markup": 1.25,
        },
        "LATAM": {
            "name": "Latin America",
            "countries": ["BR", "MX", "AR", "CL", "CO", "PE", "EC"],
            "base_currency": "USD",
            "default_markup": 1.3,
        },
        "MEA": {
            "name": "Middle East & Africa",
            "countries": ["AE", "SA", "ZA", "EG", "QA", "KW", "OM", "BH", "NG", "KE"],
            "base_currency": "USD",
            "default_markup": 1.35,
        },
    }

    DEFAULT_RATES = {
        "EUR": 1.08,
        "GBP": 1.26,
        "JPY": 0.0067,
        "CNY": 0.14,
        "AUD": 0.65,
        "SGD": 0.74,
        "CHF": 1.10,
        "KRW": 0.00075,
        "MXN": 0.055,
        "BRL": 0.19,
        "AED": 0.27,
        "SAR": 0.27,
        "NGN": 0.00067,
        "ZAR": 0.054,
    }

    # ==================== 区域解析 ====================

    def get_region_for_country(self, country_code: str) -> dict:
        """根据国家代码获取所属区域定义

        Args:
            country_code: ISO 两位国家代码（如 'US', 'DE', 'JP'）

        Returns:
            dict: {code, name, base_currency, default_markup} 或 error dict
        """
        cc = country_code.upper().strip()

        # 先从数据库精确匹配
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            row = conn.execute(
                """SELECT r.code, r.name, r.base_currency, r.default_markup
                   FROM regions r
                   JOIN region_countries rc ON r.id = rc.region_id
                   WHERE rc.country_code = ?""",
                (cc,),
            ).fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception:
            pass

        # 回退到硬编码定义
        for code, region in self.REGION_DEFINITIONS.items():
            if cc in region["countries"]:
                return {
                    "code": code,
                    "name": region["name"],
                    "base_currency": region["base_currency"],
                    "default_markup": region["default_markup"],
                }

        # 默认兜底：归入 APAC（中低利润区），USD 定价
        return {
            "code": "APAC",
            "name": "Asia Pacific",
            "base_currency": "USD",
            "default_markup": 1.25,
        }

    def get_all_regions(self) -> list:
        """获取所有区域定义

        Returns:
            list: [{code, name, base_currency, default_markup, country_count}]
        """
        results = []
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT r.*, (SELECT COUNT(*) FROM region_countries WHERE region_id=r.id) as country_count
                   FROM regions r ORDER BY r.sort_order, r.code"""
            ).fetchall()
            conn.close()
            for r in rows:
                results.append({
                    "code": r["code"],
                    "name": r["name"],
                    "base_currency": r["base_currency"],
                    "default_markup": r["default_markup"],
                    "country_count": r["country_count"],
                    "status": r["status"],
                })
        except Exception:
            # 回退到硬编码
            for code, reg in self.REGION_DEFINITIONS.items():
                results.append({
                    "code": code,
                    "name": reg["name"],
                    "base_currency": reg["base_currency"],
                    "default_markup": reg["default_markup"],
                    "country_count": len(reg.get("countries", [])),
                    "status": "active",
                })
        return results

    # ==================== 汇率管理 ====================

    def get_rate(self, from_currency: str, to_currency: str = "USD", date: Optional[str] = None) -> float:
        """获取指定日期的汇率

        Args:
            from_currency: 源币种（如 'EUR', 'GBP'）
            to_currency: 目标币种，默认 USD
            date: 日期字符串 'YYYY-MM-DD'，默认最新

        Returns:
            float: 汇率值
        """
        if from_currency == to_currency:
            return 1.0

        fc = from_currency.upper().strip()
        tc = to_currency.upper().strip()

        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            if date:
                row = conn.execute(
                    """SELECT rate FROM exchange_rates
                       WHERE from_currency=? AND to_currency=?
                       AND date=? ORDER BY date DESC LIMIT 1""",
                    (fc, tc, date),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT rate FROM exchange_rates
                       WHERE from_currency=? AND to_currency=?
                       ORDER BY date DESC LIMIT 1""",
                    (fc, tc),
                ).fetchone()
            conn.close()
            if row:
                return row["rate"]
        except Exception:
            pass

        # 回退到默认汇率
        if tc == "USD":
            rate = self.DEFAULT_RATES.get(fc)
            if rate:
                return rate
        elif from_currency == "USD" and tc in self.DEFAULT_RATES:
            return 1.0 / self.DEFAULT_RATES[tc]

        # 通过 USD 中转（间接汇率）
        if tc == "USD":
            return 1.0  # 未知币种按 1:1
        rate_to_usd = self.get_rate(fc, "USD", date)
        usd_to_target = self.get_rate("USD", tc, date)
        return rate_to_usd * usd_to_target

    def update_rate(self, from_currency: str, rate: float, to_currency: str = "USD",
                    date: Optional[str] = None, source: str = "manual") -> bool:
        """更新汇率

        Args:
            from_currency: 源币种
            rate: 汇率值
            to_currency: 目标币种，默认 USD
            date: 日期字符串，默认今天
            source: 数据来源
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import upsert_exchange_rate

            upsert_exchange_rate(
                from_currency=from_currency.upper(),
                to_currency=to_currency.upper(),
                rate=rate,
                date=date or datetime.now().strftime("%Y-%m-%d"),
                source=source,
            )
            return True
        except Exception:
            return False

    def convert(self, amount: float, from_currency: str, to_currency: str = "USD",
                date: Optional[str] = None) -> dict:
        """币种转换

        Args:
            amount: 金额
            from_currency: 源币种
            to_currency: 目标币种，默认 USD
            date: 日期

        Returns:
            dict: {amount, from_currency, to_currency, rate, converted_amount, date}
        """
        rate = self.get_rate(from_currency, to_currency, date)
        converted = round(amount * rate, 2)

        return {
            "amount": amount,
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "rate": rate,
            "converted_amount": converted,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
        }

    def get_exchange_rate_history(self, from_currency: str, to_currency: str = "USD",
                                  days: int = 30) -> list:
        """获取汇率历史

        Returns:
            list: [{date, rate, source}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            rows = conn.execute(
                """SELECT date, rate, source FROM exchange_rates
                   WHERE from_currency=? AND to_currency=?
                   ORDER BY date DESC LIMIT ?""",
                (from_currency.upper(), to_currency.upper(), days),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ==================== 市场定价策略 ====================

    def get_market_margin_targets(self, region_id: Optional[int] = None) -> list:
        """获取市场利润目标配置

        Args:
            region_id: 可选，按区域筛选

        Returns:
            list: [{region, product_category, target_margin, min_margin, competitor_factor}]
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            if region_id:
                rows = conn.execute(
                    """SELECT mp.*, r.code as region_code, r.name as region_name
                       FROM market_pricing mp
                       JOIN regions r ON mp.region_id = r.id
                       WHERE mp.region_id = ?""",
                    (region_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT mp.*, r.code as region_code, r.name as region_name
                       FROM market_pricing mp
                       JOIN regions r ON mp.region_id = r.id"""
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_pricing_coefficient(self, region_id: int, product_category: str) -> dict:
        """获取特定区域+产品类别的定价系数

        Returns:
            dict: {min_price, max_price, target_margin, min_margin, competitor_factor, markup}
        """
        default = {
            "min_price": 0,
            "max_price": 999999,
            "target_margin": 0.35,
            "min_margin": 0.20,
            "competitor_factor": 1.0,
            "markup": 1.3,
        }

        try:
            sys.path.insert(0, BASE_DIR)
            from database import get_db

            conn = get_db()
            row = conn.execute(
                """SELECT * FROM market_pricing
                   WHERE region_id=? AND product_category=?""",
                (region_id, product_category),
            ).fetchone()
            conn.close()
            if row:
                return {
                    "min_price": row["min_price"] or 0,
                    "max_price": row["max_price"] or 999999,
                    "target_margin": row["target_margin"] or 0.35,
                    "min_margin": row["min_margin"] or 0.20,
                    "competitor_factor": row["competitor_factor"] or 1.0,
                    "markup": (1.0 / (1.0 - (row["target_margin"] or 0.35)))
                    if (row["target_margin"] or 0.35) < 1.0 else 1.3,
                }
        except Exception:
            pass

        return default

    # ==================== 种子数据 ====================

    def seed_default_regions(self) -> int:
        """向数据库写入预定义的5个区域及国家映射

        Returns:
            int: 写入的区域数量
        """
        try:
            sys.path.insert(0, BASE_DIR)
            from database import seed_default_regions as db_seed

            return db_seed()
        except Exception:
            return 0

    def seed_default_rates(self) -> int:
        """写入默认汇率

        Returns:
            int: 写入的汇率数量
        """
        count = 0
        today = datetime.now().strftime("%Y-%m-%d")
        for currency, rate in self.DEFAULT_RATES.items():
            try:
                self.update_rate(currency, rate, source="seed", date=today)
                count += 1
            except Exception:
                pass
        return count


# ==================== 测试 ====================
if __name__ == "__main__":
    re = RegionEngine()

    print("=== Region Lookup ===")
    for cc in ["US", "GB", "JP", "BR", "AE", "ZZ"]:
        r = re.get_region_for_country(cc)
        print(f"  {cc} → {r['code']} ({r['base_currency']}, markup={r['default_markup']})")

    print("\n=== All Regions ===")
    for r in re.get_all_regions()[:5]:
        print(f"  {r['code']}: {r['name']} ({r['base_currency']}, {r.get('country_count',0)} countries)")

    print("\n=== Exchange Rates ===")
    for cur in ["EUR", "GBP", "JPY", "AUD", "CNY"]:
        rate = re.get_rate(cur)
        print(f"  1 {cur} = {rate} USD")

    print("\n=== Currency Conversion ===")
    conv = re.convert(1000, "EUR", "USD")
    print(f"  EUR 1000 → USD {conv['converted_amount']} (rate: {conv['rate']})")

    conv2 = re.convert(500, "USD", "EUR")
    print(f"  USD 500 → EUR {conv2['converted_amount']} (rate: {conv2['rate']})")

    print("\n=== Pricing Coefficient ===")
    pc = re.get_pricing_coefficient(1, "led_sign")
    print(f"  led_sign: target_margin={pc['target_margin']}, min_margin={pc['min_margin']}")
