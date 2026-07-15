"""V8.3: ExecutionContextBuilder — Assembles unified business context for Policy Gate

从 orders / customers / payments / risk_engine / lead_state 等分布式
数据源拼装统一的执行上下文，供 BusinessPolicyGate.evaluate() 使用。

每个数据源独立查询，build() 方法合并为一个 dict。
"""

import json
import logging
import os
import sqlite3

logger = logging.getLogger("glowforge.context_builder")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class ExecutionContextBuilder:
    """Build unified execution context for policy evaluation.

    Sources:
      - orders table      -> order status, deposit, timeline
      - customers table   -> tier, country, risk_score
      - quotes table      -> price change history
      - payments table    -> deposit/balance records
      - lead_state_engine -> current lead state
      - risk_engine       -> continuous risk score 0.0-1.0
    """

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def build(self, customer_id, task_type, payload):
        """Build complete execution context for a given task + customer.

        Returns:
            dict with keys: order, customer, payment, lead_state,
            price_change_history, customer_risk_score, production_stage,
            action_history, contract_terms, _metadata
        """
        context = {}
        order_id = payload.get("order_id")

        # Source 1: Order state (if order_id)
        if order_id:
            context["order"] = self._get_order(order_id)
            context["payment"] = self._get_payment_summary(order_id)
            context["production_stage"] = self._get_production_stage(order_id)
            context["contract_terms"] = self._parse_contract_terms(
                context["order"].get("notes", "")
            )
        else:
            context["order"] = {}
            context["payment"] = {}
            context["production_stage"] = "unknown"
            context["contract_terms"] = {}

        # Source 2: Customer profile
        context["customer"] = self._get_customer(customer_id)

        # Source 3: Lead state
        context["lead_state"] = self._get_lead_state(customer_id)

        # Source 4: Price change history
        context["price_change_history"] = self._get_price_change_history(
            customer_id, order_id
        )

        # Source 5: Customer risk score
        context["customer_risk_score"] = self._get_risk_score(customer_id)

        # Source 6: Action history
        context["action_history"] = self._get_action_history(customer_id)

        # Metadata for audit trail
        context["_metadata"] = {
            "task_type": task_type,
            "customer_id": customer_id,
            "order_id": order_id,
        }

        return context

    def _get_order(self, order_id):
        """Get order record by id."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id, status, total_amount, deposit_amount, deposit_received, "
                "       balance_amount, currency, notes, created_at "
                "FROM orders WHERE id=?",
                (order_id,),
            ).fetchone()
            conn.close()
            if row:
                d = dict(row)
                d["deposit_received"] = bool(d.get("deposit_received", 0))
                return d
        except Exception as e:
            logger.warning("[ContextBuilder] _get_order(%s): %s", order_id, e)
        return {"id": order_id, "status": "unknown", "deposit_received": False}

    def _get_customer(self, customer_id):
        """Get customer profile."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id, name, country, language, status as lead_status "
                "FROM customers WHERE id=?",
                (customer_id,),
            ).fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception as e:
            logger.warning("[ContextBuilder] _get_customer(%s): %s", customer_id, e)
        return {"id": customer_id, "country": "", "lead_status": "NEW"}

    def _get_lead_state(self, customer_id):
        """Get current lead state."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT lead_state FROM customers WHERE id=?",
                (customer_id,),
            ).fetchone()
            conn.close()
            return row["lead_state"] if row else "NEW"
        except Exception:
            return "NEW"

    def _get_payment_summary(self, order_id):
        """Aggregate payment info for an order."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN type='deposit' THEN amount ELSE 0 END), 0) as deposit_total, "
                "       COALESCE(SUM(CASE WHEN type='balance' THEN amount ELSE 0 END), 0) as balance_total, "
                "       COUNT(*) as payment_count "
                "FROM payments WHERE order_id=?",
                (order_id,),
            ).fetchone()
            conn.close()
            if row:
                d = dict(row)
                d["deposit_received"] = d["deposit_total"] > 0
                return d
        except Exception as e:
            logger.warning("[ContextBuilder] _get_payment_summary(%s): %s", order_id, e)
        return {"deposit_total": 0, "balance_total": 0, "deposit_received": False}

    def _get_price_change_history(self, customer_id, order_id=None):
        """Get recent price changes from quotes (DESC by created_at)."""
        try:
            conn = self._get_conn()
            params = [customer_id]
            sql = (
                "SELECT quote_no, total_amount, currency, status, created_at "
                "FROM quotes WHERE customer_id=? ORDER BY created_at DESC LIMIT 10"
            )
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[ContextBuilder] _get_price_change_history(%s): %s",
                           customer_id, e)
        return []

    def _get_risk_score(self, customer_id):
        """Get customer risk score from RiskEngine. Returns 0.0 on failure."""
        try:
            from safety.risk_engine import RiskEngine
            re = RiskEngine()
            result = re.score(customer_id, {}, {"customer_id": customer_id})
            return result.get("overall", 0.0)
        except Exception:
            return 0.0

    def _get_action_history(self, customer_id):
        """Get recent actions from lead_action_log."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT action, created_at FROM lead_action_log "
                "WHERE customer_id=? ORDER BY created_at DESC LIMIT 20",
                (customer_id,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _get_production_stage(self, order_id):
        """Derive production stage from order status + timeline."""
        try:
            order = self._get_order(order_id)
            status = order.get("status", "unknown")

            # Map order status to production stage
            stage_map = {
                "pending_approval": "pending_approval",
                "deposit_pending": "deposit_pending",
                "confirmed": "confirmed",
                "in_production": "in_production",
                "completed": "completed",
                "shipped": "shipped",
                "delivered": "delivered",
                "cancelled": "cancelled",
            }
            return stage_map.get(status, status)
        except Exception:
            return "unknown"

    @staticmethod
    def _parse_contract_terms(notes):
        """Parse structured contract terms from order notes JSON."""
        if not notes:
            return {}
        try:
            data = json.loads(notes)
            if isinstance(data, dict):
                return {
                    "cancellation_policy": data.get("cancellation_policy", ""),
                    "refund_policy": data.get("refund_policy", ""),
                    "modification_fee": data.get("modification_fee", 0),
                }
        except (json.JSONDecodeError, Exception):
            pass
        return {}
