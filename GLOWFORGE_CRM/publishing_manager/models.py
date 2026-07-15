"""Data access layer for publishing_manager tables."""
import json
import time
from .db import get_db

# ============================================================
# Platform Accounts
# ============================================================

def create_platform_account(user_id, platform, account_name="", account_id="",
                            access_token="", refresh_token="", token_expiry=0,
                            api_key="", api_secret="", daily_limit=5,
                            timezone_offset=0, target_market=""):
    db = get_db()
    c = db.execute("""INSERT INTO pub_platform_accounts
        (user_id, platform, account_name, account_id, access_token, refresh_token,
         token_expiry, api_key, api_secret, daily_limit, timezone_offset, target_market)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, platform, account_name, account_id, access_token, refresh_token,
         token_expiry, api_key, api_secret, daily_limit, timezone_offset, target_market))
    db.commit()
    pk = c.lastrowid
    db.close()
    return pk


def get_platform_account(account_id):
    db = get_db()
    row = db.execute("SELECT * FROM pub_platform_accounts WHERE id=?", (account_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def list_platform_accounts(user_id=None, platform=None):
    db = get_db()
    sql = "SELECT * FROM pub_platform_accounts WHERE 1=1"
    params = []
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(user_id)
    if platform:
        sql += " AND platform=?"
        params.append(platform)
    sql += " ORDER BY platform, account_name"
    rows = db.execute(sql, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_platform_account(account_id, **kwargs):
    allowed = {"account_name", "account_id", "access_token", "refresh_token",
               "token_expiry", "api_key", "api_secret", "is_active", "daily_limit",
               "timezone_offset", "target_market"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db = get_db()
    db.execute(f"UPDATE pub_platform_accounts SET {set_clause} WHERE id=?",
               list(updates.values()) + [account_id])
    db.commit()
    db.close()
    return True


def delete_platform_account(account_id):
    db = get_db()
    db.execute("DELETE FROM pub_platform_accounts WHERE id=?", (account_id,))
    db.commit()
    db.close()


# ============================================================
# Content Items
# ============================================================

def create_content_item(user_id, title="", description="", tags="", category="",
                        video_path="", thumbnail_path="", duration_seconds=0,
                        source_video_id=0, ai_generated=0, source_script="",
                        status="draft"):
    db = get_db()
    c = db.execute("""INSERT INTO pub_content_items
        (user_id, title, description, tags, category, video_path, thumbnail_path,
         duration_seconds, source_video_id, ai_generated, source_script, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, title, description, tags, category, video_path, thumbnail_path,
         duration_seconds, source_video_id, ai_generated, source_script, status))
    db.commit()
    pk = c.lastrowid
    db.close()
    return pk


def get_content_item(item_id):
    db = get_db()
    row = db.execute("SELECT * FROM pub_content_items WHERE id=?", (item_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def list_content_items(user_id=None, status=None, limit=50, offset=0):
    db = get_db()
    sql = "SELECT * FROM pub_content_items WHERE 1=1"
    params = []
    if user_id is not None:
        sql += " AND user_id=?"
        params.append(user_id)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(sql, params).fetchall()
    total = db.execute("SELECT COUNT(*) FROM pub_content_items").fetchone()[0]
    db.close()
    return [dict(r) for r in rows], total


def update_content_item(item_id, **kwargs):
    allowed = {"title", "description", "tags", "category", "video_path",
               "thumbnail_path", "duration_seconds", "status", "source_script"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db = get_db()
    db.execute(f"UPDATE pub_content_items SET {set_clause} WHERE id=?",
               list(updates.values()) + [item_id])
    db.commit()
    db.close()
    return True


def delete_content_item(item_id):
    db = get_db()
    db.execute("DELETE FROM pub_content_items WHERE id=?", (item_id,))
    db.commit()
    db.close()


# ============================================================
# Publish Schedules
# ============================================================

def create_schedule(content_item_id, platform_account_id, scheduled_at,
                    priority=0, frequency_group=""):
    db = get_db()
    c = db.execute("""INSERT INTO pub_schedules
        (content_item_id, platform_account_id, scheduled_at, priority, frequency_group)
        VALUES (?,?,?,?,?)""",
        (content_item_id, platform_account_id, scheduled_at, priority, frequency_group))
    db.commit()
    pk = c.lastrowid
    db.close()
    return pk


def get_schedule(schedule_id):
    db = get_db()
    row = db.execute("SELECT * FROM pub_schedules WHERE id=?", (schedule_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def list_schedules(content_item_id=None, platform_account_id=None, status=None,
                   start_at=None, end_at=None, limit=100, offset=0):
    db = get_db()
    sql = """SELECT s.*, c.title as content_title, c.duration_seconds,
             p.platform, p.account_name as platform_account_name
             FROM pub_schedules s
             LEFT JOIN pub_content_items c ON s.content_item_id = c.id
             LEFT JOIN pub_platform_accounts p ON s.platform_account_id = p.id
             WHERE 1=1"""
    params = []
    if content_item_id:
        sql += " AND s.content_item_id=?"
        params.append(content_item_id)
    if platform_account_id:
        sql += " AND s.platform_account_id=?"
        params.append(platform_account_id)
    if status:
        sql += " AND s.status=?"
        params.append(status)
    if start_at:
        sql += " AND s.scheduled_at>=?"
        params.append(start_at)
    if end_at:
        sql += " AND s.scheduled_at<=?"
        params.append(end_at)
    sql += " ORDER BY s.scheduled_at ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(sql, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_schedule(schedule_id, **kwargs):
    allowed = {"scheduled_at", "status", "platform_post_id", "platform_url",
               "error_message", "priority", "retry_count", "published_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db = get_db()
    db.execute(f"UPDATE pub_schedules SET {set_clause} WHERE id=?",
               list(updates.values()) + [schedule_id])
    db.commit()
    db.close()
    return True


def delete_schedule(schedule_id):
    db = get_db()
    db.execute("DELETE FROM pub_schedules WHERE id=?", (schedule_id,))
    db.commit()
    db.close()
