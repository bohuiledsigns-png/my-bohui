"""Database initialization and helper for publishing_manager."""
import sqlite3
import os

DB_PATH = ""

# SQL for creating all 11 tables
CREATE_TABLES_SQL = """

CREATE TABLE IF NOT EXISTS pub_platform_accounts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    platform            TEXT NOT NULL,
    account_name        TEXT NOT NULL DEFAULT '',
    account_id          TEXT NOT NULL DEFAULT '',
    access_token        TEXT NOT NULL DEFAULT '',
    refresh_token       TEXT NOT NULL DEFAULT '',
    token_expiry        INTEGER NOT NULL DEFAULT 0,
    api_key             TEXT NOT NULL DEFAULT '',
    api_secret          TEXT NOT NULL DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,
    daily_limit         INTEGER NOT NULL DEFAULT 5,
    timezone_offset     INTEGER NOT NULL DEFAULT 0,
    target_market       TEXT NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_content_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    source_video_id     INTEGER NOT NULL DEFAULT 0,
    title               TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    tags                TEXT NOT NULL DEFAULT '',
    category            TEXT NOT NULL DEFAULT '',
    video_path          TEXT NOT NULL DEFAULT '',
    thumbnail_path      TEXT NOT NULL DEFAULT '',
    duration_seconds    INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'draft',
    ai_generated        INTEGER NOT NULL DEFAULT 0,
    source_script       TEXT NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_schedules (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id     INTEGER NOT NULL,
    platform_account_id INTEGER NOT NULL,
    scheduled_at        INTEGER NOT NULL DEFAULT 0,
    published_at        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',
    platform_post_id    TEXT NOT NULL DEFAULT '',
    platform_url        TEXT NOT NULL DEFAULT '',
    frequency_group     TEXT NOT NULL DEFAULT '',
    error_message       TEXT NOT NULL DEFAULT '',
    priority            INTEGER NOT NULL DEFAULT 0,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (content_item_id) REFERENCES pub_content_items(id),
    FOREIGN KEY (platform_account_id) REFERENCES pub_platform_accounts(id)
);

CREATE TABLE IF NOT EXISTS pub_publish_queue (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id         INTEGER NOT NULL,
    content_item_id     INTEGER NOT NULL,
    platform_account_id INTEGER NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued',
    attempt_number      INTEGER NOT NULL DEFAULT 1,
    last_error          TEXT NOT NULL DEFAULT '',
    locked_at           INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (schedule_id) REFERENCES pub_schedules(id)
);

CREATE TABLE IF NOT EXISTS pub_video_analytics (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id     INTEGER NOT NULL,
    platform_account_id INTEGER NOT NULL,
    date                TEXT NOT NULL,
    views               INTEGER NOT NULL DEFAULT 0,
    unique_viewers      INTEGER NOT NULL DEFAULT 0,
    likes               INTEGER NOT NULL DEFAULT 0,
    comments            INTEGER NOT NULL DEFAULT 0,
    shares              INTEGER NOT NULL DEFAULT 0,
    saves               INTEGER NOT NULL DEFAULT 0,
    completion_rate     REAL NOT NULL DEFAULT 0.0,
    avg_watch_seconds   REAL NOT NULL DEFAULT 0.0,
    drop_off_25         REAL NOT NULL DEFAULT 0.0,
    drop_off_50         REAL NOT NULL DEFAULT 0.0,
    drop_off_75         REAL NOT NULL DEFAULT 0.0,
    replay_rate         REAL NOT NULL DEFAULT 0.0,
    reach               INTEGER NOT NULL DEFAULT 0,
    recommendation_vol  INTEGER NOT NULL DEFAULT 0,
    trending_score      REAL NOT NULL DEFAULT 0.0,
    data_source         TEXT NOT NULL DEFAULT 'manual',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (content_item_id) REFERENCES pub_content_items(id),
    FOREIGN KEY (platform_account_id) REFERENCES pub_platform_accounts(id),
    UNIQUE(content_item_id, platform_account_id, date)
);

CREATE TABLE IF NOT EXISTS pub_comments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id     INTEGER NOT NULL,
    platform_account_id INTEGER NOT NULL,
    platform_comment_id TEXT NOT NULL DEFAULT '',
    parent_comment_id   INTEGER NOT NULL DEFAULT 0,
    author_name         TEXT NOT NULL DEFAULT '',
    author_id           TEXT NOT NULL DEFAULT '',
    text                TEXT NOT NULL DEFAULT '',
    sentiment           TEXT NOT NULL DEFAULT 'neutral',
    sentiment_score     REAL NOT NULL DEFAULT 0.0,
    keywords            TEXT NOT NULL DEFAULT '',
    is_replied          INTEGER NOT NULL DEFAULT 0,
    auto_reply_sent     INTEGER NOT NULL DEFAULT 0,
    auto_reply_template TEXT NOT NULL DEFAULT '',
    reply_text          TEXT NOT NULL DEFAULT '',
    replied_at          INTEGER NOT NULL DEFAULT 0,
    customer_type       TEXT NOT NULL DEFAULT '',
    conversion_stage    TEXT NOT NULL DEFAULT '',
    flagged             INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (content_item_id) REFERENCES pub_content_items(id)
);

CREATE TABLE IF NOT EXISTS pub_auto_reply_templates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform            TEXT NOT NULL DEFAULT '',
    keyword_pattern     TEXT NOT NULL DEFAULT '',
    sentiment_filter    TEXT NOT NULL DEFAULT '',
    reply_template      TEXT NOT NULL DEFAULT '',
    reply_type          TEXT NOT NULL DEFAULT 'text',
    is_active           INTEGER NOT NULL DEFAULT 1,
    usage_count         INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_production_schedule (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    date                TEXT NOT NULL,
    task_type           TEXT NOT NULL,
    duration_minutes    INTEGER NOT NULL DEFAULT 60,
    content_item_id     INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'planned',
    notes               TEXT NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    report_type         TEXT NOT NULL,
    period_start        TEXT NOT NULL,
    period_end          TEXT NOT NULL,
    title               TEXT NOT NULL DEFAULT '',
    summary             TEXT NOT NULL DEFAULT '',
    total_published     INTEGER NOT NULL DEFAULT 0,
    total_views         INTEGER NOT NULL DEFAULT 0,
    total_engagement    INTEGER NOT NULL DEFAULT 0,
    engagement_rate     REAL NOT NULL DEFAULT 0.0,
    platform_breakdown  TEXT NOT NULL DEFAULT '',
    trend_data          TEXT NOT NULL DEFAULT '',
    issues              TEXT NOT NULL DEFAULT '',
    suggestions         TEXT NOT NULL DEFAULT '',
    roi_analysis        TEXT NOT NULL DEFAULT '',
    is_auto_generated   INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_ai_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    analysis_type       TEXT NOT NULL,
    platform            TEXT NOT NULL DEFAULT '',
    content_item_id     INTEGER NOT NULL DEFAULT 0,
    input_summary       TEXT NOT NULL DEFAULT '',
    result              TEXT NOT NULL DEFAULT '',
    suggestions         TEXT NOT NULL DEFAULT '',
    confidence_score    REAL NOT NULL DEFAULT 0.0,
    is_applied          INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pub_audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL DEFAULT 0,
    action              TEXT NOT NULL,
    entity_type         TEXT NOT NULL,
    entity_id           INTEGER NOT NULL DEFAULT 0,
    details             TEXT NOT NULL DEFAULT '',
    ip_address          TEXT NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_pub_schedules_status ON pub_schedules(status);
CREATE INDEX IF NOT EXISTS idx_pub_schedules_scheduled ON pub_schedules(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_pub_queue_status ON pub_publish_queue(status);
CREATE INDEX IF NOT EXISTS idx_pub_analytics_date ON pub_video_analytics(date);
CREATE INDEX IF NOT EXISTS idx_pub_comments_sentiment ON pub_comments(sentiment);
CREATE INDEX IF NOT EXISTS idx_pub_comments_content ON pub_comments(content_item_id);
CREATE INDEX IF NOT EXISTS idx_pub_reports_period ON pub_reports(report_type, period_start);
"""


def set_db_path(path):
    global DB_PATH
    DB_PATH = path


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path):
    set_db_path(db_path)
    conn = get_db()
    try:
        conn.executescript(CREATE_TABLES_SQL)
        conn.commit()
        print(f"[PublishingDB] Initialized at {db_path}")
    finally:
        conn.close()
