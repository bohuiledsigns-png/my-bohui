"""Risk Engine — 6-dimension continuous risk scoring

Replaces the 3-level categorical risk in ACTION_RISK / _assess_risk()
with a multi-dimensional continuous 0.0–1.0 scoring system.

Dimensions:
  - customer_value: lead status, order history
  - amount: price magnitude, discount aggressiveness
  - country: market risk
  - language/culture: communication risk
  - profit: margin impact
  - compliance: prohibited content, regulatory risk
"""
import json
import logging
import os
import sqlite3

logger = logging.getLogger("glowforge.risk_engine")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# Default dimension weights (sum = 1.0)
_DEFAULT_WEIGHTS = {
    "customer_value": 0.15,
    "amount": 0.20,
    "country": 0.15,
    "language": 0.10,
    "profit": 0.25,
    "compliance": 0.15,
}

# lead_status → customer_value risk mapping
_LEAD_STATUS_RISK = {
    "CLOSED_WON": 0.1,
    "HOT": 0.2,
    "NEGOTIATING": 0.3,
    "QUOTED": 0.4,
    "PRICING": 0.4,
    "REQUESTED_PRICE": 0.5,
    "INTERESTED": 0.6,
    "QUALIFYING": 0.6,
    "NEW": 0.7,
    "COLD": 0.8,
    "UNKNOWN": 0.5,
}

# Country risk groups
_COUNTRY_RISK_MAP = {
    # Low-risk markets
    "US": 0.2, "CA": 0.2, "GB": 0.2, "DE": 0.2, "FR": 0.2,
    "AU": 0.2, "NZ": 0.2, "JP": 0.2, "KR": 0.2, "SG": 0.2,
    # Medium-risk markets
    "AE": 0.5, "SA": 0.5, "QA": 0.5, "KW": 0.5, "OM": 0.5,
    "BH": 0.5, "MY": 0.5, "TH": 0.5, "VN": 0.5, "IN": 0.5,
    "BR": 0.5, "MX": 0.5,
    # High-risk / unknown
    "RU": 0.8, "CN": 0.7,
}

_MAX_PRICE_THRESHOLD = 10000.0


class RiskEngine:
    """6-dimension continuous risk scorer"""

    def __init__(self, registry=None, weights=None):
        self._registry = registry
        self._weights = weights or dict(_DEFAULT_WEIGHTS)

    def score(self, customer_id, action, context):
        """Score risk for a given action.

        Returns:
            dict: {
                dimensions: {customer_value, amount, country, language, profit, compliance},
                overall: float (0.0–1.0),
                level: str (low|medium|high|critical),
                factors: [str]
            }
        """
        try:
            dims = {}
            factors = []

            dims["customer_value"] = self._score_customer_value(action, context)
            dims["amount"] = self._score_amount(action, context)
            dims["country"] = self._score_country(action, context)
            dims["language"] = self._score_language(action, context)
            dims["profit"] = self._score_profit(action, context)
            dims["compliance"] = self._score_compliance(action, context)

            overall = sum(
                self._weights.get(name, 0.0) * dims[name]
                for name in ("customer_value", "amount", "country", "language", "profit", "compliance")
            )
            overall = max(0.0, min(1.0, overall))

            level = self._determine_risk_level(overall)

            for name, val in dims.items():
                if val >= 0.5:
                    factors.append(f"{name}={val:.2f}")

            return {
                "dimensions": dims,
                "overall": overall,
                "level": level,
                "factors": factors,
            }
        except Exception as e:
            logger.warning("RiskEngine.score failed: %s", e)
            return {
                "dimensions": {k: 0.3 for k in _DEFAULT_WEIGHTS},
                "overall": 0.3,
                "level": "medium",
                "factors": ["scoring_error"],
            }

    def _score_customer_value(self, action, context):
        """Customer value risk based on lead status and order history"""
        lead_state = (context.get("lead_state") or "UNKNOWN").upper()
        risk = _LEAD_STATUS_RISK.get(lead_state, 0.5)
        # Having orders reduces risk
        if context.get("has_orders"):
            risk = max(0.0, risk - 0.2)
        return risk

    def _score_amount(self, action, context):
        """Amount risk based on price magnitude and discount"""
        price = action.get("price") or 0
        discount = action.get("discount") or 0

        # Price magnitude
        price_risk = min(1.0, price / _MAX_PRICE_THRESHOLD) if price > 0 else 0.3

        # Discount factor
        if discount > 25:
            price_risk = min(1.0, price_risk + 0.3)
        elif discount > 15:
            price_risk = min(1.0, price_risk + 0.2)
        elif discount > 10:
            price_risk = min(1.0, price_risk + 0.1)

        return price_risk

    def _score_country(self, action, context):
        """Country risk based on customer location"""
        country = (context.get("customer_country") or "").upper()
        if not country:
            return 0.3
        return _COUNTRY_RISK_MAP.get(country, 0.8)

    def _score_language(self, action, context):
        """Language/cultural risk"""
        content = action.get("content", "") or ""
        translation = context.get("translation", "") or ""

        # If no translation available for content → higher risk
        if content and not translation:
            return 0.4
        return 0.1

    def _score_profit(self, action, context):
        """Profit impact risk"""
        price = action.get("price") or 0
        discount = action.get("discount") or 0

        # High discount with price → margin risk
        if price > 0 and discount > 15:
            return 0.6
        if price > 0 and discount > 25:
            return 0.8

        # No price info = medium risk
        if not price:
            return 0.3
        return 0.1

    def _score_compliance(self, action, context):
        """Compliance risk — prohibited patterns, guarantees"""
        content = action.get("content", "") or ""
        content_lower = content.lower()

        risk_indicators = [
            ("guarantee", 0.7),
            ("100%", 0.8),
            ("money back", 0.8),
            ("no risk", 0.7),
            ("fixed exchange", 0.6),
            ("password", 0.9),
            ("secret", 0.8),
        ]

        max_risk = 0.1
        for keyword, risk in risk_indicators:
            if keyword in content_lower:
                max_risk = max(max_risk, risk)
        return max_risk

    def _determine_risk_level(self, score):
        """Map continuous score to categorical level"""
        if score < 0.3:
            return "low"
        elif score < 0.5:
            return "medium"
        elif score < 0.7:
            return "high"
        return "critical"

    def log_event(self, customer_id, action, context, result, decision_id=None):
        """Log risk event to risk_events table"""
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute(
                    """INSERT INTO risk_events
                       (decision_id, customer_id, action_type,
                        dim_customer_value, dim_amount, dim_country, dim_language, dim_profit, dim_compliance,
                        overall_score, risk_level, factors_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        decision_id or "",
                        customer_id,
                        action.get("type", ""),
                        result["dimensions"].get("customer_value", 0),
                        result["dimensions"].get("amount", 0),
                        result["dimensions"].get("country", 0),
                        result["dimensions"].get("language", 0),
                        result["dimensions"].get("profit", 0),
                        result["dimensions"].get("compliance", 0),
                        result["overall"],
                        result["level"],
                        json.dumps(result.get("factors", []), ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
