"""Commercial Reality Layer — DB table definitions

三张核心表：
  1. order_fulfillment     — 订单履约状态机（生产/质检/发货/交期偏差）
  2. payment_lifecycle     — 资金生命周期（意向→定金→尾款→退款/纠纷）
  3. stripe_events         — Stripe Webhook 幂等去重
"""
import logging
import sqlite3

logger = logging.getLogger("glowforge.commercial_reality.db")


def init_tables(db_path: str):
    """创建 commercial_reality 层的全部数据表。幂等（IF NOT EXISTS）。

    设计原则：
    - 不改动现有的 orders 表结构
    - 通过 order_id 外键关联，不破坏原有 schema
    - 所有状态有 CHECK 约束，防止脏数据
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript("""
            -- ───────── 订单履约追踪表 ─────────
            CREATE TABLE IF NOT EXISTS order_fulfillment (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id          INTEGER NOT NULL UNIQUE,
                fulfillment_id    TEXT    NOT NULL UNIQUE,

                -- 五个核心状态
                production_status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(production_status IN (
                        'PENDING','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED'
                    )),
                qc_status         TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(qc_status IN (
                        'PENDING','PASSED','FAILED','NOT_REQUIRED'
                    )),
                shipment_status   TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(shipment_status IN (
                        'PENDING','BOOKED','SHIPPED','DELIVERED','CANCELLED'
                    )),
                payment_status    TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(payment_status IN (
                        'PENDING','DEPOSIT_PAID','FULL_PAID','REFUNDING','DISPUTED'
                    )),

                -- 交期承诺与现实偏差
                promised_delivery_date TEXT DEFAULT '',
                actual_delivery_date   TEXT DEFAULT '',
                delay_alert_sent       INTEGER NOT NULL DEFAULT 0,
                delay_reason           TEXT    DEFAULT '',

                -- 异常标记
                is_fulfillable    INTEGER NOT NULL DEFAULT 1,
                risk_level        TEXT NOT NULL DEFAULT 'LOW'
                    CHECK(risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),

                -- 人工备注 / 老板决策
                internal_note     TEXT DEFAULT '',
                boss_decision     TEXT DEFAULT '',

                -- 时间戳
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (order_id) REFERENCES orders(id)
            );

            CREATE INDEX IF NOT EXISTS idx_of_order       ON order_fulfillment(order_id);
            CREATE INDEX IF NOT EXISTS idx_of_risk        ON order_fulfillment(risk_level);
            CREATE INDEX IF NOT EXISTS idx_of_delivery    ON order_fulfillment(promised_delivery_date);
            CREATE INDEX IF NOT EXISTS idx_of_fulfillable ON order_fulfillment(is_fulfillable);

            -- ───────── 资金生命周期表 ─────────
            CREATE TABLE IF NOT EXISTS payment_lifecycle (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id          INTEGER NOT NULL,
                payment_id        TEXT    NOT NULL UNIQUE,

                -- 资金状态机
                stage             TEXT NOT NULL DEFAULT 'INTENT'
                    CHECK(stage IN (
                        'INTENT','COMMITMENT','DEPOSIT_PAID',
                        'FULL_PAID','REFUNDING','DISPUTED','CLOSED'
                    )),

                amount            REAL    NOT NULL DEFAULT 0,
                currency          TEXT    NOT NULL DEFAULT 'USD',
                payment_method    TEXT    DEFAULT '',
                payment_link      TEXT    DEFAULT '',

                -- 收款确认
                paid_at           TIMESTAMP,
                payer_name        TEXT    DEFAULT '',
                transaction_ref   TEXT    DEFAULT '',

                -- 退款 / 纠纷
                refund_amount     REAL    DEFAULT 0,
                refund_reason     TEXT    DEFAULT '',
                dispute_status    TEXT    DEFAULT ''
                    CHECK(dispute_status IN ('','OPEN','RESOLVED','CLOSED')),

                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (order_id) REFERENCES orders(id)
            );

            CREATE INDEX IF NOT EXISTS idx_pl_order    ON payment_lifecycle(order_id);
            CREATE INDEX IF NOT EXISTS idx_pl_stage    ON payment_lifecycle(stage);
            CREATE INDEX IF NOT EXISTS idx_pl_paid_at  ON payment_lifecycle(paid_at);

            -- ───────── Stripe Webhook 幂等表 ─────────
            CREATE TABLE IF NOT EXISTS stripe_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id      TEXT    NOT NULL UNIQUE,
                type          TEXT    NOT NULL,
                order_id      INTEGER NOT NULL DEFAULT 0,
                session_id    TEXT    DEFAULT '',
                payment_intent_id TEXT DEFAULT '',
                processed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_se_event_id ON stripe_events(event_id);

            -- ───────── WhatsApp 多号轮换 ─────────
            CREATE TABLE IF NOT EXISTS wa_accounts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL UNIQUE,
                profile_dir     TEXT    NOT NULL,
                cdp_port        INTEGER NOT NULL DEFAULT 9223,
                status          TEXT    NOT NULL DEFAULT 'inactive'
                    CHECK(status IN ('active','standby','offline','disabled','inactive')),
                priority        INTEGER NOT NULL DEFAULT 0,
                last_health_at  TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        logger.info("[CommercialReality] Tables initialized: order_fulfillment, payment_lifecycle, stripe_events, wa_accounts")
    except Exception as e:
        logger.error("[CommercialReality] Table init failed: %s", e)
        raise
    finally:
        conn.close()
