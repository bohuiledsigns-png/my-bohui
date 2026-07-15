"""Policy Engine — DB-backed policy rule engine

Replaces hardcoded BusinessPolicy.POLICY_RULES with DB-stored rules
from the 'policies' table. Supports hot-reload via version cache.

Graceful degradation: if policies table is missing or empty,
falls back to module-level BusinessPolicy.POLICY_RULES.
"""
import json
import logging
import os
import sqlite3
from copy import deepcopy

logger = logging.getLogger("glowforge.policy_engine")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")

# Policy check_type → evaluator method name mapping
_CHECK_TYPE_DISPATCH = {
    "country_allowed": "_evaluate_country_allowed",
    "max_discount": "_evaluate_max_discount",
    "minimum_margin": "_evaluate_minimum_margin",
    "tier_discount": "_evaluate_tier_discount",
    "product_status": "_evaluate_product_status",
    "market_readiness": "_evaluate_market_readiness",
    "price_change_frequency": "_evaluate_price_change_frequency",
}


class PolicyEngine:
    """DB-backed policy rule engine with version-based hot-reload"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH
        self._cache = None
        self._cache_version = 0
        self._fallback = False
        self._policies_loaded = False
        self.load_policies()

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA query_only = 1")
        return conn

    def _get_conn_rw(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load_policies(self, force_reload=False):
        """Load active policies from DB into cache.

        Falls back to BusinessPolicy.POLICY_RULES if table missing or empty.
        """
        if self._cache is not None and not force_reload:
            return self._cache

        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM policies WHERE is_active = 1 ORDER BY priority, policy_id"
            ).fetchall()
            conn.close()

            if rows:
                policies = []
                for r in rows:
                    p = dict(r)
                    try:
                        p["config"] = json.loads(p.get("config_json", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        p["config"] = {}
                    policies.append(p)
                self._cache = policies
                self._cache_version = max(p.get("version", 1) for p in policies)
                self._fallback = False
                self._policies_loaded = True
                return policies

            # Empty table — try fallback
            policies = self._load_fallback_policies()
            self._cache = policies
            self._cache_version = 0
            self._fallback = True
            self._policies_loaded = False
            return policies

        except (sqlite3.OperationalError, Exception):
            policies = self._load_fallback_policies()
            self._cache = policies
            self._cache_version = 0
            self._fallback = True
            self._policies_loaded = False
            return policies

    def _load_fallback_policies(self):
        """Fallback: load from BusinessPolicy module when DB unavailable"""
        try:
            from strategy_engine.policy.business_policy import POLICY_RULES
        except ImportError:
            return []
        policies = []
        for rule in POLICY_RULES:
            config = {}
            for k, v in rule.items():
                if k not in ("id", "category", "rule", "severity", "check_type"):
                    config[k] = v
            policies.append({
                "policy_id": rule.get("id", "UNKNOWN"),
                "category": rule.get("category", ""),
                "rule": rule.get("rule", ""),
                "severity": rule.get("severity", "hard"),
                "check_type": rule.get("check_type", ""),
                "config": config,
                "priority": 100 if rule.get("severity") == "hard" else 200,
                "version": 1,
            })
        return policies

    def get_active_policies(self):
        """Get cached policies, with lightweight hot-reload check"""
        if self._cache is not None and not self._fallback:
            try:
                conn = self._get_conn()
                max_v = conn.execute("SELECT MAX(version) as v FROM policies").fetchone()["v"] or 0
                conn.close()
                if max_v > self._cache_version:
                    self.load_policies(force_reload=True)
            except Exception:
                pass
        return self._cache or []

    def check_policies(self, action, context, unified_state):
        """Evaluate all active policies against the given action.

        Returns:
            dict: {passed: bool, rules: list[violations], total: int}
        """
        rules = []
        context = context or {}
        unified_state = unified_state or {}

        for policy in self.get_active_policies():
            method_name = _CHECK_TYPE_DISPATCH.get(policy.get("check_type", ""))
            if method_name is None:
                continue
            method = getattr(self, method_name, None)
            if method is None:
                continue
            try:
                violation = method(policy, action, context, unified_state)
                if violation:
                    rules.append(violation)
            except Exception as e:
                logger.warning("Policy %s evaluation error: %s", policy.get("policy_id"), e)

        passed = not any(r.get("severity") == "hard" for r in rules)
        return {"passed": passed, "rules": rules, "total": len(rules),
                "policies_loaded": self._policies_loaded}

    # ── Per-check-type evaluators ──

    def _evaluate_country_allowed(self, policy, action, context, state):
        """POLICY_001: customer country must be in allowed list"""
        country = context.get("customer_country", "")
        if not country:
            return None
        allowed = policy.get("config", {}).get("allowed_countries", [])
        if allowed and country not in allowed:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"国家 {country} 不在许可列表",
                "severity": policy["severity"],
            }
        return None

    def _evaluate_max_discount(self, policy, action, context, state):
        """POLICY_003: discount must not exceed max"""
        discount = action.get("discount")
        if discount is None:
            return None
        max_disc = policy.get("config", {}).get("max_discount", 0.25)
        if discount > max_disc * 100:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"折扣 {discount}% 超过上限 {max_disc*100:.0f}%",
                "severity": policy["severity"],
            }
        return None

    def _evaluate_minimum_margin(self, policy, action, context, state):
        """POLICY_002: minimum margin check (uses unified_state pricing)"""
        price = action.get("price")
        if not price:
            return None
        min_margin = policy.get("config", {}).get("min_margin", 0.25)
        # Rough margin estimation from action context
        history = state.get("pricing_history", [])
        if history:
            last = history[0]
            last_price = last.get("amount") or 0
            if last_price > 0 and (price / last_price - 1) < min_margin:
                return {
                    "policy_id": policy["policy_id"],
                    "rule": policy["rule"],
                    "detail": f"报价 {price} 可能导致利润率低于 {min_margin*100:.0f}%",
                    "severity": policy["severity"],
                }
        return None

    def _evaluate_tier_discount(self, policy, action, context, state):
        """POLICY_004: tier-based discount limits"""
        discount = action.get("discount")
        if discount is None:
            return None
        tier = context.get("customer_tier", "LOW")
        limits = policy.get("config", {}).get("tier_limits", {})
        limit = limits.get(tier, 5)
        if discount > limit:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"{tier} 客户折扣 {discount}% > 上限 {limit}%",
                "severity": policy["severity"],
            }
        return None

    def _evaluate_product_status(self, policy, action, context, state):
        """POLICY_005: product must be in allowed status"""
        product_status = action.get("product_status") or state.get("product_status")
        if not product_status:
            return None
        allowed = policy.get("config", {}).get("allowed_statuses", ["active"])
        if product_status not in allowed:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"产品状态 {product_status} 不允许",
                "severity": policy["severity"],
            }
        return None

    def _evaluate_market_readiness(self, policy, action, context, state):
        """POLICY_006: minimum inquiries before market entry"""
        inquiries = state.get("inquiry_count", 0) or state.get("message_count", 0)
        threshold = policy.get("config", {}).get("min_inquiries", 3)
        if inquiries < threshold:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"询盘数 {inquiries} < 最低 {threshold}",
                "severity": policy["severity"],
            }
        return None

    def _evaluate_price_change_frequency(self, policy, action, context, state):
        """POLICY_007: cool-down between price changes"""
        history = state.get("pricing_history", [])
        if len(history) < 2:
            return None
        cooldown = policy.get("config", {}).get("cooldown_days", 30)
        # Simplified: flag if too many changes in short time
        recent = [h for h in history[:5] if h.get("status") == "pending"]
        if len(recent) >= 2:
            return {
                "policy_id": policy["policy_id"],
                "rule": policy["rule"],
                "detail": f"最近 {len(recent)} 个报价仍待处理，不宜改价",
                "severity": policy["severity"],
            }
        return None

    # ── Seed / CRUD ──

    def seed_default_policies(self):
        """Seed DB from BusinessPolicy.POLICY_RULES if policies table is empty.

        Returns: int — number of rows seeded (0 = already seeded or fallback)
        """
        try:
            conn = self._get_conn_rw()
            count = conn.execute("SELECT COUNT(*) as c FROM policies").fetchone()[0]
            if count > 0:
                conn.close()
                return 0

            from strategy_engine.policy.business_policy import POLICY_RULES

            seeded = 0
            for rule in POLICY_RULES:
                config = {}
                for k, v in rule.items():
                    if k not in ("id", "category", "rule", "severity", "check_type"):
                        config[k] = v
                conn.execute(
                    """INSERT OR IGNORE INTO policies
                       (policy_id, category, rule, severity, check_type, config_json, priority, version)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        rule.get("id", ""),
                        rule.get("category", ""),
                        rule.get("rule", ""),
                        rule.get("severity", "hard"),
                        rule.get("check_type", ""),
                        json.dumps(config, ensure_ascii=False),
                        100 if rule.get("severity") == "hard" else 200,
                    ),
                )
                seeded += 1

            conn.commit()
            conn.close()
            self.load_policies(force_reload=True)
            return seeded
        except Exception as e:
            logger.warning("seed_default_policies failed: %s", e)
            return 0

    def add_policy(self, data):
        """Add a new policy. Returns the policy_id."""
        try:
            conn = self._get_conn_rw()
            config = {k: v for k, v in data.items()
                      if k not in ("policy_id", "category", "rule", "severity", "check_type")}
            conn.execute(
                """INSERT INTO policies
                   (policy_id, category, rule, severity, check_type, config_json, priority, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    data.get("policy_id", ""),
                    data.get("category", ""),
                    data.get("rule", ""),
                    data.get("severity", "hard"),
                    data.get("check_type", ""),
                    json.dumps(config, ensure_ascii=False),
                    data.get("priority", 100),
                ),
            )
            conn.commit()
            conn.close()
            self.load_policies(force_reload=True)
            return data.get("policy_id", "")
        except Exception as e:
            logger.warning("add_policy failed: %s", e)
            return ""

    def update_policy(self, policy_id, data):
        """Update an existing policy. Increments version."""
        try:
            conn = self._get_conn_rw()
            fields = []
            params = []
            for k in ("category", "rule", "severity", "check_type", "priority", "is_active"):
                if k in data:
                    fields.append(f"{k} = ?")
                    params.append(data[k])
            if any(k not in ("id", "policy_id", "category", "rule", "severity", "check_type", "priority", "is_active") for k in data):
                # Rebuild config_json from remaining keys
                config = {k: v for k, v in data.items()
                          if k not in ("category", "rule", "severity", "check_type", "priority", "is_active", "policy_id")}
                fields.append("config_json = ?")
                params.append(json.dumps(config, ensure_ascii=False))
            fields.append("version = version + 1")
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(policy_id)
            conn.execute(
                f"UPDATE policies SET {', '.join(fields)} WHERE policy_id = ?",
                params,
            )
            conn.commit()
            conn.close()
            self.load_policies(force_reload=True)
            return True
        except Exception as e:
            logger.warning("update_policy failed: %s", e)
            return False

    def delete_policy(self, policy_id):
        """Soft-delete a policy (set is_active=0)."""
        try:
            conn = self._get_conn_rw()
            conn.execute("UPDATE policies SET is_active=0, version=version+1 WHERE policy_id=?", (policy_id,))
            conn.commit()
            conn.close()
            self.load_policies(force_reload=True)
            return True
        except Exception:
            return False
