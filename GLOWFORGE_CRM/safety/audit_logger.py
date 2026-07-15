"""AuditLogger — Structured audit logging for the Decision Firewall

Replaces file-based _log_decision() with DB-backed structured logging
into decision_log, risk_events, and firewall_events tables.

Dual-writes alongside file logging during transition for backward compatibility.
"""
import json
import logging
import os
import sqlite3

logger = logging.getLogger("glowforge.audit_logger")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "crm_data.db")


class AuditLogger:
    """Structured DB audit logger for firewall decisions"""

    def __init__(self, db_path=None):
        self._db_path = db_path or DB_PATH

    def _get_conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def log_decision(self, decision):
        """Log a firewall decision to decision_log table.

        Returns decision_id on success, None on failure.
        """
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO decision_log
                       (decision_id, customer_id, action_type, action_json, context_json,
                        verdict, risk_score, reason, checks_json, blocked_rules,
                        latency_ms, source_agent)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        decision.get("decision_id", ""),
                        decision.get("customer_id"),
                        decision.get("action", {}).get("type", ""),
                        json.dumps(decision.get("action", {}), ensure_ascii=False),
                        json.dumps(decision.get("context", {}), ensure_ascii=False),
                        decision.get("verdict", "ALLOW"),
                        decision.get("risk_score_continuous", decision.get("risk_score", 0)),
                        decision.get("reason", ""),
                        json.dumps(decision.get("checks", {}), ensure_ascii=False, default=str),
                        json.dumps(decision.get("blocked_rules", []), ensure_ascii=False),
                        decision.get("latency_ms", 0),
                        decision.get("action", {}).get("source_agent", ""),
                    ),
                )
                conn.commit()
                return decision.get("decision_id")
            finally:
                conn.close()
        except Exception as e:
            logger.warning("AuditLogger.log_decision failed: %s", e)
            return None

    def log_risk_event(self, customer_id, action_type, risk_result, decision_id=None):
        """Log a risk scoring event to risk_events table"""
        try:
            conn = self._get_conn()
            try:
                dims = risk_result.get("dimensions", {})
                conn.execute(
                    """INSERT INTO risk_events
                       (decision_id, customer_id, action_type,
                        dim_customer_value, dim_amount, dim_country, dim_language, dim_profit, dim_compliance,
                        overall_score, risk_level, factors_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        decision_id or "",
                        customer_id,
                        action_type,
                        dims.get("customer_value", 0),
                        dims.get("amount", 0),
                        dims.get("country", 0),
                        dims.get("language", 0),
                        dims.get("profit", 0),
                        dims.get("compliance", 0),
                        risk_result.get("overall", 0),
                        risk_result.get("level", "low"),
                        json.dumps(risk_result.get("factors", []), ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("AuditLogger.log_risk_event failed: %s", e)

    def log_firewall_event(self, customer_id, action_type, check_name, verdict, detail=""):
        """Log a per-check firewall event"""
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO firewall_events
                       (customer_id, action_type, check_name, verdict, detail)
                       VALUES (?, ?, ?, ?, ?)""",
                    (customer_id, action_type, check_name, verdict, detail),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("AuditLogger.log_firewall_event failed: %s", e)

    # ── Query methods ──

    def get_decisions(self, customer_id=None, verdict=None, limit=50):
        """Query decision_log with optional filters"""
        try:
            conn = self._get_conn()
            try:
                conn.row_factory = sqlite3.Row
                parts = []
                params = []
                if customer_id is not None:
                    parts.append("customer_id = ?")
                    params.append(customer_id)
                if verdict:
                    parts.append("verdict = ?")
                    params.append(verdict)
                where = ("WHERE " + " AND ".join(parts)) if parts else ""
                rows = conn.execute(
                    f"SELECT * FROM decision_log {where} ORDER BY created_at DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("AuditLogger.get_decisions failed: %s", e)
            return []

    def get_risk_events(self, customer_id=None, level=None, limit=50):
        """Query risk_events with optional filters"""
        try:
            conn = self._get_conn()
            try:
                conn.row_factory = sqlite3.Row
                parts = []
                params = []
                if customer_id is not None:
                    parts.append("customer_id = ?")
                    params.append(customer_id)
                if level:
                    parts.append("risk_level = ?")
                    params.append(level)
                where = ("WHERE " + " AND ".join(parts)) if parts else ""
                rows = conn.execute(
                    f"SELECT * FROM risk_events {where} ORDER BY overall_score DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.warning("AuditLogger.get_risk_events failed: %s", e)
            return []

    def get_escalations(self, limit=50):
        """Get recent ESCALATE decisions"""
        return self.get_decisions(verdict="ESCALATE", limit=limit)

    def get_stats(self):
        """Get aggregated audit stats"""
        try:
            conn = self._get_conn()
            try:
                conn.row_factory = sqlite3.Row
                stats = {}

                # Verdict distribution
                rows = conn.execute(
                    "SELECT verdict, COUNT(*) as c FROM decision_log GROUP BY verdict"
                ).fetchall()
                stats["verdicts"] = {r["verdict"]: r["c"] for r in rows}

                # Avg latency
                row = conn.execute(
                    "SELECT AVG(latency_ms) as avg_lat FROM decision_log"
                ).fetchone()
                stats["avg_latency_ms"] = round(row["avg_lat"] or 0, 1)

                # Escalation rate
                total = conn.execute("SELECT COUNT(*) as c FROM decision_log").fetchone()["c"]
                escalated = conn.execute(
                    "SELECT COUNT(*) as c FROM decision_log WHERE verdict='ESCALATE'"
                ).fetchone()["c"]
                stats["escalation_rate"] = round(escalated / total, 3) if total > 0 else 0

                return stats
            finally:
                conn.close()
        except Exception:
            return {}
