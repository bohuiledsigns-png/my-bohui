"""Currency Optimizer — 汇率+心理定价系统

不是简单的汇率换算，而是"本地心理可接受价格重构"。

示例：
  US: $310
  UK: £249 (不是$310×0.79=£245, 而是心理定价£249)
  AE: 1,150 AED (不是$310×3.67=1,138, 而是心理定价1,150)
"""

import sys
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


class CurrencyOptimizer:
    """货币优化器 — 心理定价+汇率换算"""

    # 汇率配置（内部固定，与客户报价隔离）
    EXCHANGE_RATES = {
        "USD": 1.0,
        "EUR": 0.92,
        "GBP": 0.79,
        "AED": 3.67,
        "SAR": 3.75,
        "CAD": 1.37,
        "AUD": 1.54,
        "JPY": 157.0,
        "SGD": 1.35,
        "MYR": 4.72,
    }

    # 心理定价规则（每个货币的"好看"价格尾数）
    PSYCHOLOGICAL_PRICING = {
        "USD": {"round_to": 10, "use_99": False, "preferred_ends": [9, 5, 0]},
        "EUR": {"round_to": 10, "use_99": False, "preferred_ends": [9, 5, 0]},
        "GBP": {"round_to": 10, "use_99": True, "preferred_ends": [9, 5]},
        "AED": {"round_to": 50, "use_99": False, "preferred_ends": [0, 5]},
        "SAR": {"round_to": 50, "use_99": False, "preferred_ends": [0, 5]},
        "CAD": {"round_to": 10, "use_99": False, "preferred_ends": [9, 5]},
        "AUD": {"round_to": 10, "use_99": True, "preferred_ends": [9, 5]},
        "JPY": {"round_to": 1000, "use_99": False, "preferred_ends": [0, 800]},
        "SGD": {"round_to": 10, "use_99": False, "preferred_ends": [9, 8]},
        "MYR": {"round_to": 10, "use_99": True, "preferred_ends": [9, 8]},
    }

    # 货币符号
    CURRENCY_SYMBOLS = {
        "USD": "$", "EUR": "€", "GBP": "£",
        "AED": "AED ", "SAR": "SAR ",
        "CAD": "C$", "AUD": "A$",
        "JPY": "¥", "SGD": "S$", "MYR": "RM",
    }

    @staticmethod
    def convert(amount_usd: float, to_currency: str = "USD",
                apply_psychological: bool = True) -> dict:
        """将USD金额转换为目标货币的心理定价

        Args:
            amount_usd: USD金额
            to_currency: 目标货币代码
            apply_psychological: 是否应用心理定价规则

        Returns:
            dict: {
                amount_usd, currency, rate,
                raw_converted, psychological_price,
                display_price, symbol
            }
        """
        to_currency = to_currency.upper()
        rate = CurrencyOptimizer.EXCHANGE_RATES.get(to_currency, 1.0)

        # 汇率换算
        raw_converted = round(amount_usd / CurrencyOptimizer.EXCHANGE_RATES.get("USD", 1.0) * rate, 2)

        if not apply_psychological:
            return {
                "amount_usd": round(amount_usd, 2),
                "currency": to_currency,
                "rate": rate,
                "raw_converted": raw_converted,
                "psychological_price": raw_converted,
                "display_price": f"{CurrencyOptimizer.CURRENCY_SYMBOLS.get(to_currency, '')}{raw_converted:,.0f}",
                "symbol": CurrencyOptimizer.CURRENCY_SYMBOLS.get(to_currency, ""),
            }

        # 心理定价
        psych_rules = CurrencyOptimizer.PSYCHOLOGICAL_PRICING.get(to_currency, {})
        round_to = psych_rules.get("round_to", 10)
        use_99 = psych_rules.get("use_99", False)
        preferred_ends = psych_rules.get("preferred_ends", [9, 0])

        # 四舍五入到指定精度
        psychological = round(raw_converted / round_to) * round_to

        # 对某些货币使用 .99 结尾
        if use_99:
            psychological = psychological - 1 if psychological % 10 != 0 else psychological - 1
        else:
            # 调整尾数到优选值
            last_digit = psychological % 10
            if last_digit not in preferred_ends:
                # 向下调整到最近的优选尾数
                target = max(d for d in preferred_ends if d <= last_digit) if any(d <= last_digit for d in preferred_ends) else preferred_ends[0]
                psychological = (psychological // 10) * 10 + target

        if psychological <= 0:
            psychological = raw_converted

        symbol = CurrencyOptimizer.CURRENCY_SYMBOLS.get(to_currency, "")
        formatted = f"{symbol}{psychological:,.0f}"
        if use_99:
            formatted = f"{symbol}{psychological:,.0f}".replace(".00", ".99")

        return {
            "amount_usd": round(amount_usd, 2),
            "currency": to_currency,
            "rate": rate,
            "raw_converted": raw_converted,
            "psychological_price": psychological,
            "display_price": formatted,
            "symbol": symbol,
        }

    @staticmethod
    def get_localized_price(amount_usd: float, country: str) -> dict:
        """根据国家获取本地化价格

        Args:
            amount_usd: USD金额
            country: 国家代码

        Returns:
            dict: {display_price, currency, psychological_price}
        """
        # 国家→货币映射
        country_currency = {
            "US": "USD", "CA": "CAD",
            "GB": "GBP", "UK": "GBP",
            "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
            "AE": "AED", "SA": "SAR", "QA": "AED",
            "JP": "JPY", "AU": "AUD",
            "SG": "SGD", "MY": "MYR",
        }

        currency = country_currency.get(country.upper(), "USD")
        return CurrencyOptimizer.convert(amount_usd, currency)

    @staticmethod
    def get_all_prices(amount_usd: float) -> list:
        """获取所有货币的本地化价格

        Returns:
            list: [{currency, display_price, psychological_price, ...}]
        """
        results = []
        for currency in CurrencyOptimizer.EXCHANGE_RATES:
            result = CurrencyOptimizer.convert(amount_usd, currency)
            results.append({
                "currency": currency,
                "display_price": result["display_price"],
                "psychological_price": result["psychological_price"],
                "raw_converted": result["raw_converted"],
                "rate": result["rate"],
            })
        return results


# 快捷入口
optimizer = CurrencyOptimizer()


def convert_price(amount_usd: float, to_currency: str = "USD") -> dict:
    return CurrencyOptimizer.convert(amount_usd, to_currency)


def get_localized_price(amount_usd: float, country: str) -> dict:
    return CurrencyOptimizer.get_localized_price(amount_usd, country)
