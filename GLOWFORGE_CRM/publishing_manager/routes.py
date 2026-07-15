"""Route definitions for publishing_manager Blueprint."""
import json
import time
import os
from flask import jsonify, request, render_template, session, redirect

from . import publishing_bp
from . import models as m


def _login_required():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


# ============================================================
# Page Routes
# ============================================================

@publishing_bp.route("/dashboard")
def page_dashboard():
    return render_template("publishing/dashboard.html")


@publishing_bp.route("/accounts")
def page_accounts():
    return render_template("publishing/accounts.html")


@publishing_bp.route("/accounts/add")
def page_account_add():
    return redirect("/publishing/accounts")


@publishing_bp.route("/accounts/<int:account_id>/edit")
def page_account_edit(account_id):
    return redirect("/publishing/accounts")


@publishing_bp.route("/schedule")
def page_schedule():
    return render_template("publishing/schedule.html")


@publishing_bp.route("/content")
def page_content():
    return render_template("publishing/content_list.html")


@publishing_bp.route("/content/<int:item_id>")
def page_content_detail(item_id):
    return render_template("publishing/content_detail.html", item_id=item_id)


@publishing_bp.route("/analytics")
def page_analytics():
    return render_template("publishing/analytics.html")


@publishing_bp.route("/comments")
def page_comments():
    return render_template("publishing/comments.html")


@publishing_bp.route("/reports")
def page_reports():
    return render_template("publishing/reports.html")


@publishing_bp.route("/work-time")
def page_work_time():
    return render_template("publishing/work_time.html")


@publishing_bp.route("/ai-insights")
def page_ai_insights():
    return render_template("publishing/ai_insights.html")


# ============================================================
# API: Dashboard Stats
# ============================================================

@publishing_bp.route("/api/stats")
def api_dashboard_stats():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    # TEMP DEBUG - remove later
    print(f"[PUBLISHING DEBUG] /api/stats user_id={user_id} session_keys={list(session.keys())} session_userid={session.get('user_id')}")
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        total_content = db.execute("SELECT COUNT(*) FROM pub_content_items WHERE user_id=?",
                                   (user_id,)).fetchone()[0]
        total_scheduled = db.execute(
            "SELECT COUNT(*) FROM pub_schedules s JOIN pub_content_items c ON s.content_item_id=c.id WHERE c.user_id=? AND s.status='pending'",
            (user_id,)).fetchone()[0]
        total_published = db.execute(
            "SELECT COUNT(*) FROM pub_schedules s JOIN pub_content_items c ON s.content_item_id=c.id WHERE c.user_id=? AND s.status='success'",
            (user_id,)).fetchone()[0]
        total_views = db.execute(
            "SELECT COALESCE(SUM(views),0) FROM pub_video_analytics a JOIN pub_content_items c ON a.content_item_id=c.id WHERE c.user_id=?",
            (user_id,)).fetchone()[0]
        accounts = db.execute(
            "SELECT platform, COUNT(*) as cnt FROM pub_platform_accounts WHERE user_id=? AND is_active=1 GROUP BY platform",
            (user_id,)).fetchall()
        recent = db.execute(
            """SELECT s.*, c.title, p.platform, p.account_name
               FROM pub_schedules s
               JOIN pub_content_items c ON s.content_item_id=c.id
               JOIN pub_platform_accounts p ON s.platform_account_id=p.id
               WHERE c.user_id=? ORDER BY s.scheduled_at DESC LIMIT 10""",
            (user_id,)).fetchall()
    finally:
        db.close()
    return jsonify({
        "total_content": total_content,
        "total_scheduled": total_scheduled,
        "total_published": total_published,
        "total_views": total_views,
        "accounts": {r["platform"]: r["cnt"] for r in accounts},
        "recent": [dict(r) for r in recent]
    })


# ============================================================
# API: Platform Accounts
# ============================================================

@publishing_bp.route("/api/accounts", methods=["GET"])
def api_list_accounts():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    rows = m.list_platform_accounts(user_id)
    return jsonify(rows)


@publishing_bp.route("/api/accounts", methods=["POST"])
def api_create_account():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    data = request.json or {}
    pk = m.create_platform_account(
        user_id=user_id,
        platform=data.get("platform", ""),
        account_name=data.get("account_name", ""),
        account_id=data.get("account_id", ""),
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        api_key=data.get("api_key", ""),
        api_secret=data.get("api_secret", ""),
        daily_limit=int(data.get("daily_limit", 5)),
        timezone_offset=int(data.get("timezone_offset", 0)),
        target_market=data.get("target_market", "")
    )
    return jsonify({"id": pk})


@publishing_bp.route("/api/accounts/<int:account_id>", methods=["PUT"])
def api_update_account(account_id):
    data = request.json or {}
    m.update_platform_account(account_id, **data)
    return jsonify({"ok": True})


@publishing_bp.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def api_delete_account(account_id):
    m.delete_platform_account(account_id)
    return jsonify({"ok": True})


# ============================================================
# API: Content Items
# ============================================================

@publishing_bp.route("/api/content", methods=["GET"])
def api_list_content():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    items, total = m.list_content_items(user_id, status, limit, offset)
    return jsonify({"items": items, "total": total})


@publishing_bp.route("/api/content", methods=["POST"])
def api_create_content():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    data = request.json or {}
    pk = m.create_content_item(
        user_id=user_id,
        title=data.get("title", ""),
        description=data.get("description", ""),
        tags=data.get("tags", ""),
        category=data.get("category", ""),
        video_path=data.get("video_path", ""),
        thumbnail_path=data.get("thumbnail_path", ""),
        duration_seconds=int(data.get("duration_seconds", 0)),
        ai_generated=int(data.get("ai_generated", 0)),
        source_script=data.get("source_script", "")
    )
    return jsonify({"id": pk})


@publishing_bp.route("/api/content/<int:item_id>", methods=["GET"])
def api_get_content(item_id):
    item = m.get_content_item(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@publishing_bp.route("/api/content/<int:item_id>", methods=["PUT"])
def api_update_content(item_id):
    data = request.json or {}
    m.update_content_item(item_id, **data)
    return jsonify({"ok": True})


@publishing_bp.route("/api/content/<int:item_id>", methods=["DELETE"])
def api_delete_content(item_id):
    m.delete_content_item(item_id)
    return jsonify({"ok": True})


@publishing_bp.route("/api/content/<int:item_id>/analytics", methods=["GET"])
def api_content_analytics(item_id):
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        stats = db.execute("""
            SELECT COALESCE(SUM(views),0) as views,
                   COALESCE(SUM(likes),0) as likes,
                   COALESCE(SUM(comments),0) as comments,
                   COALESCE(SUM(shares),0) as shares,
                   COALESCE(AVG(completion_rate),0) as avg_completion
            FROM pub_video_analytics WHERE content_item_id=?""", (item_id,)).fetchone()
        recent_comments = db.execute("""
            SELECT c.*, p.platform
            FROM pub_comments c
            LEFT JOIN pub_platform_accounts p ON c.platform_account_id = p.id
            WHERE c.content_item_id=? ORDER BY c.created_at DESC LIMIT 10""", (item_id,)).fetchall()
        platform_stats = db.execute("""
            SELECT p.platform, SUM(a.views) as views, SUM(a.likes) as likes
            FROM pub_video_analytics a
            JOIN pub_platform_accounts p ON a.platform_account_id = p.id
            WHERE a.content_item_id=? GROUP BY p.platform""", (item_id,)).fetchall()
    finally:
        db.close()
    return jsonify({
        "stats": dict(stats),
        "recent_comments": [dict(r) for r in recent_comments],
        "platform_stats": [dict(r) for r in platform_stats]
    })


# ============================================================
# API: Schedules
# ============================================================

@publishing_bp.route("/api/schedules", methods=["GET"])
def api_list_schedules():
    start_at = request.args.get("start_at")
    end_at = request.args.get("end_at")
    status = request.args.get("status")
    rows = m.list_schedules(
        status=status,
        start_at=int(start_at) if start_at else None,
        end_at=int(end_at) if end_at else None,
        limit=int(request.args.get("limit", 100)),
        offset=int(request.args.get("offset", 0))
    )
    return jsonify(rows)


@publishing_bp.route("/api/schedules", methods=["POST"])
def api_create_schedule():
    data = request.json or {}
    pk = m.create_schedule(
        content_item_id=data.get("content_item_id"),
        platform_account_id=data.get("platform_account_id"),
        scheduled_at=data.get("scheduled_at", int(time.time())),
        priority=data.get("priority", 0),
        frequency_group=data.get("frequency_group", "")
    )
    return jsonify({"id": pk})


@publishing_bp.route("/api/schedules/<int:schedule_id>", methods=["PUT"])
def api_update_schedule(schedule_id):
    data = request.json or {}
    m.update_schedule(schedule_id, **data)
    return jsonify({"ok": True})


@publishing_bp.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
def api_delete_schedule(schedule_id):
    m.delete_schedule(schedule_id)
    return jsonify({"ok": True})


# ============================================================
# API: Import from Video Tool
# ============================================================

@publishing_bp.route("/api/scan-video-tool", methods=["GET"])
def api_scan_video_tool():
    """Scan video_tool_server.py output directory for generated videos."""
    video_dir = os.environ.get("VIDEO_TOOL_OUTPUT",
                                "D:/Bohui_Global_Push/GLOWFORGE_CRM/output")
    generations_log = os.path.join(
        os.path.dirname(video_dir) if not video_dir.endswith("output") else
        os.path.dirname(video_dir),
        "generation_log.json"
    )
    results = []
    # Read generation_log.json if it exists
    if os.path.exists(generations_log):
        try:
            with open(generations_log, "r", encoding="utf-8") as f:
                logs = json.load(f)
            for entry in logs[-50:]:  # last 50 entries
                results.append({
                    "source_id": entry.get("id", 0),
                    "product": entry.get("product_name", entry.get("product", "")),
                    "prompt": entry.get("prompt", ""),
                    "video_path": entry.get("video_path", entry.get("result_path", "")),
                    "duration": entry.get("duration", 0),
                    "created_at": entry.get("created_at", 0),
                    "language": entry.get("language", "en")
                })
        except (json.JSONDecodeError, OSError):
            pass
    # Also scan the output directory for video files
    if os.path.isdir(video_dir):
        for fname in sorted(os.listdir(video_dir), reverse=True)[:50]:
            if fname.endswith((".mp4", ".webm", ".mov")):
                fpath = os.path.join(video_dir, fname)
                results.append({
                    "source_id": 0,
                    "product": os.path.splitext(fname)[0],
                    "video_path": fpath,
                    "duration": 0,
                    "created_at": os.path.getmtime(fpath)
                })
    return jsonify(results)


@publishing_bp.route("/api/import-video", methods=["POST"])
def api_import_video():
    """Import a video from video_tool into the publishing system."""
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    data = request.json or {}
    pk = m.create_content_item(
        user_id=user_id,
        title=data.get("title", "Imported Video"),
        description=data.get("description", ""),
        tags=data.get("tags", ""),
        video_path=data.get("video_path", ""),
        duration_seconds=int(data.get("duration", 0)),
        source_video_id=int(data.get("source_id", 0)),
        ai_generated=1,
        source_script=data.get("prompt", ""),
        status="ready"
    )
    return jsonify({"id": pk})


# ============================================================
# API: Scheduler Control
# ============================================================

@publishing_bp.route("/api/engine/status", methods=["GET"])
def api_engine_status():
    from .scheduler import _scheduler_thread, _scheduler_stop
    return jsonify({
        "running": _scheduler_thread is not None and _scheduler_thread.is_alive(),
        "stop_requested": _scheduler_stop is not None and _scheduler_stop.is_set()
    })


@publishing_bp.route("/api/engine/trigger", methods=["POST"])
def api_engine_trigger():
    from .scheduler import _process_queue, _enqueue_due_schedules
    db_path = __import__("publishing_manager.db", fromlist=["get_db"]).DB_PATH
    _enqueue_due_schedules(db_path)
    _process_queue(db_path)
    return jsonify({"ok": True})


# ============================================================
# API: Analytics
# ============================================================

@publishing_bp.route("/api/analytics/summary")
def api_analytics_summary():
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        # Total views across all time
        total_views = db.execute("SELECT COALESCE(SUM(views),0) FROM pub_video_analytics").fetchone()[0]
        total_likes = db.execute("SELECT COALESCE(SUM(likes),0) FROM pub_video_analytics").fetchone()[0]
        total_comments = db.execute("SELECT COALESCE(SUM(comments),0) FROM pub_video_analytics").fetchone()[0]
        total_shares = db.execute("SELECT COALESCE(SUM(shares),0) FROM pub_video_analytics").fetchone()[0]
        total_saves = db.execute("SELECT COALESCE(SUM(saves),0) FROM pub_video_analytics").fetchone()[0]

        # Published count
        total_published = db.execute("SELECT COUNT(*) FROM pub_schedules WHERE status='success'").fetchone()[0]

        # Engagement rate (likes+comments+shares)/views
        engagement_rate = 0
        if total_views > 0:
            engagement_rate = round((total_likes + total_comments + total_shares) / total_views * 100, 2)

        # Avg completion rate
        avg_completion = db.execute("SELECT COALESCE(AVG(completion_rate),0) FROM pub_video_analytics WHERE views>0").fetchone()[0]

        # Per-platform breakdown
        platforms = db.execute("""
            SELECT p.platform,
                   COUNT(DISTINCT a.content_item_id) as videos,
                   COALESCE(SUM(a.views),0) as views,
                   COALESCE(SUM(a.likes),0) as likes,
                   COALESCE(SUM(a.comments),0) as comments,
                   COALESCE(SUM(a.shares),0) as shares,
                   COALESCE(AVG(a.completion_rate),0) as avg_completion
            FROM pub_video_analytics a
            JOIN pub_platform_accounts p ON a.platform_account_id = p.id
            GROUP BY p.platform
        """).fetchall()

        # Last 30 days trend
        thirty_days_ago = int(time.time()) - 86400 * 30
        trends = db.execute("""
            SELECT date, SUM(views) as views, SUM(likes) as likes, SUM(comments) as comments, SUM(shares) as shares
            FROM pub_video_analytics
            WHERE date >= ?
            GROUP BY date ORDER BY date ASC LIMIT 60
        """, (thirty_days_ago,)).fetchall()
    finally:
        db.close()

    return jsonify({
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_shares": total_shares,
        "total_saves": total_saves,
        "total_published": total_published,
        "engagement_rate": engagement_rate,
        "avg_completion_rate": round(avg_completion, 2),
        "platforms": [dict(r) for r in platforms],
        "trends": [dict(r) for r in trends]
    })


@publishing_bp.route("/api/analytics/top-content")
def api_analytics_top_content():
    limit = int(request.args.get("limit", 10))
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        rows = db.execute("""
            SELECT a.content_item_id, c.title,
                   SUM(a.views) as views, SUM(a.likes) as likes,
                   SUM(a.comments) as comments, SUM(a.shares) as shares,
                   AVG(a.completion_rate) as avg_completion
            FROM pub_video_analytics a
            JOIN pub_content_items c ON a.content_item_id = c.id
            GROUP BY a.content_item_id
            ORDER BY SUM(a.views) DESC LIMIT ?
        """, (limit,)).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])


@publishing_bp.route("/api/analytics/seed", methods=["POST"])
def api_analytics_seed():
    """Generate sample analytics data for testing."""
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        accounts = db.execute("SELECT id FROM pub_platform_accounts").fetchall()
        content = db.execute("SELECT id FROM pub_content_items").fetchall()
        if not accounts or not content:
            return jsonify({"error": "Need at least 1 account and 1 content item"}), 400

        import random
        random.seed(42)
        count = 0
        # Generate 60 days of data for each content-account pair
        for c in content:
            for a in accounts:
                for day_offset in range(60):
                    d = int(time.time()) - 86400 * day_offset
                    date_str = time.strftime("%Y-%m-%d", time.localtime(d))
                    views = random.randint(50, 500)
                    db.execute("""INSERT OR REPLACE INTO pub_video_analytics
                        (content_item_id, platform_account_id, date, views, unique_viewers,
                         likes, comments, shares, saves, completion_rate, avg_watch_seconds)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (c["id"], a["id"], date_str, views, int(views*0.7),
                         int(views*0.05), int(views*0.02), int(views*0.01), int(views*0.03),
                         round(random.uniform(0.3, 0.8), 2), round(random.uniform(10, 45), 1)))
                    count += 1
        db.commit()
    finally:
        db.close()
    return jsonify({"seeded": count})


# ============================================================
# API: Comments
# ============================================================

@publishing_bp.route("/api/comments", methods=["GET"])
def api_list_comments():
    sentiment = request.args.get("sentiment")
    content_id = request.args.get("content_item_id")
    platform = request.args.get("platform")
    status = request.args.get("status")  # unreplied, replied, flagged
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        sql = """SELECT c.*, ct.title as content_title, p.platform, p.account_name as platform_name
                 FROM pub_comments c
                 LEFT JOIN pub_content_items ct ON c.content_item_id = ct.id
                 LEFT JOIN pub_platform_accounts p ON c.platform_account_id = p.id
                 WHERE 1=1"""
        params = []
        if sentiment:
            sql += " AND c.sentiment=?"
            params.append(sentiment)
        if content_id:
            sql += " AND c.content_item_id=?"
            params.append(content_id)
        if platform:
            sql += " AND p.platform=?"
            params.append(platform)
        if status == "unreplied":
            sql += " AND (c.is_replied IS NULL OR c.is_replied=0)"
        elif status == "replied":
            sql += " AND c.is_replied=1"
        elif status == "flagged":
            sql += " AND c.flagged=1"
        sql += " ORDER BY c.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        total_sql = "SELECT COUNT(*) FROM pub_comments c LEFT JOIN pub_platform_accounts p ON c.platform_account_id=p.id WHERE 1=1"
        total_params = []
        if sentiment:
            total_sql += " AND c.sentiment=?"
            total_params.append(sentiment)
        if content_id:
            total_sql += " AND c.content_item_id=?"
            total_params.append(content_id)
        if platform:
            total_sql += " AND p.platform=?"
            total_params.append(platform)
        if status == "unreplied":
            total_sql += " AND (c.is_replied IS NULL OR c.is_replied=0)"
        elif status == "replied":
            total_sql += " AND c.is_replied=1"
        elif status == "flagged":
            total_sql += " AND c.flagged=1"
        total = db.execute(total_sql, total_params).fetchone()[0]
        rows = db.execute(sql, params).fetchall()
    finally:
        db.close()
    return jsonify({"items": [dict(r) for r in rows], "total": total})


@publishing_bp.route("/api/comments/reply", methods=["POST"])
def api_reply_comment():
    data = request.json or {}
    comment_id = data.get("comment_id")
    reply_text = (data.get("reply_text") or "").strip()
    if not comment_id or not reply_text:
        return jsonify({"error": "comment_id and reply_text required"}), 400
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        db.execute("UPDATE pub_comments SET is_replied=1, reply_text=?, replied_at=? WHERE id=?",
                   (reply_text, int(time.time()), comment_id))
        db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


@publishing_bp.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def api_delete_comment(comment_id):
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        db.execute("DELETE FROM pub_comments WHERE id=?", (comment_id,))
        db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


@publishing_bp.route("/api/comments/seed", methods=["POST"])
def api_seed_comments():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    import random
    random.seed(99)
    sample_comments = [
        ("Great video! Very helpful.", "positive", 0.85, "customer", "interested"),
        ("Nice work, keep it up!", "positive", 0.7, "customer", "awareness"),
        ("How much does this cost?", "neutral", 0.1, "customer", "consideration"),
        ("Can you ship to Europe?", "neutral", 0.0, "customer", "consideration"),
        ("Terrible quality, waste of time", "negative", -0.8, "customer", "lost"),
        ("Love the LED signs! 🔥", "positive", 0.9, "customer", "interested"),
        ("What materials do you use?", "neutral", 0.2, "customer", "consideration"),
        ("Not what I expected", "negative", -0.4, "customer", "awareness"),
        ("Please send me a quote", "positive", 0.6, "lead", "consideration"),
        ("I want to order one!", "positive", 0.95, "customer", "conversion"),
    ]
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        accounts = db.execute("SELECT id FROM pub_platform_accounts").fetchall()
        content = db.execute("SELECT id FROM pub_content_items").fetchall()
        count = 0
        for c in content:
            for a in accounts:
                for text, sentiment, score, ctype, stage in sample_comments:
                    db.execute("""INSERT INTO pub_comments
                        (content_item_id, platform_account_id, platform_comment_id,
                         author_name, text, sentiment, sentiment_score,
                         customer_type, conversion_stage, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (c["id"], a["id"], f"seed_{int(time.time())}_{count}",
                         f"User_{random.randint(100,999)}", text, sentiment, score,
                         ctype, stage, int(time.time()) - random.randint(0, 86400 * 7)))
                    count += 1
        db.commit()
    finally:
        db.close()
    return jsonify({"seeded": count})


# ============================================================
# API: Auto-Reply Templates
# ============================================================

@publishing_bp.route("/api/reply-templates", methods=["GET"])
def api_list_templates():
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        rows = db.execute("SELECT * FROM pub_auto_reply_templates ORDER BY is_active DESC, id ASC").fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])


@publishing_bp.route("/api/reply-templates", methods=["POST"])
def api_create_template():
    data = request.json or {}
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        c = db.execute("""INSERT INTO pub_auto_reply_templates
            (platform, keyword_pattern, sentiment_filter, reply_template, reply_type, is_active)
            VALUES (?,?,?,?,?,?)""",
            (data.get("platform", ""), data.get("keyword_pattern", ""),
             data.get("sentiment_filter", ""), data.get("reply_template", ""),
             data.get("reply_type", "text"), int(data.get("is_active", 1))))
        db.commit()
        pk = c.lastrowid
    finally:
        db.close()
    return jsonify({"id": pk})


@publishing_bp.route("/api/reply-templates/<int:tmpl_id>", methods=["DELETE"])
def api_delete_template(tmpl_id):
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        db.execute("DELETE FROM pub_auto_reply_templates WHERE id=?", (tmpl_id,))
        db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})


# ============================================================
# API: AI Insights
# ============================================================

@publishing_bp.route("/api/ai-insights")
def api_ai_insights():
    """Generate AI-powered insights from analytics data."""
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        now = int(time.time())
        month_ago = now - 86400 * 30
        week_ago = now - 86400 * 7

        cur_views = db.execute(
            "SELECT COALESCE(SUM(views),0) FROM pub_video_analytics WHERE date >= ?",
            (week_ago,)).fetchone()[0]
        prev_views = db.execute(
            "SELECT COALESCE(SUM(views),0) FROM pub_video_analytics WHERE date >= ? AND date < ?",
            (month_ago, week_ago)).fetchone()[0]

        views_change = 0
        if prev_views > 0:
            views_change = round((cur_views - prev_views) / prev_views * 100, 1)

        best = db.execute("""
            SELECT c.title, SUM(a.views) as views, AVG(a.completion_rate) as comp
            FROM pub_video_analytics a JOIN pub_content_items c ON a.content_item_id=c.id
            GROUP BY a.content_item_id ORDER BY SUM(a.views) DESC LIMIT 3
        """).fetchall()

        best_day = db.execute("""
            SELECT CAST(strftime('%w', date) AS INTEGER) as dow, AVG(views) as avg_views
            FROM pub_video_analytics WHERE views > 0
            GROUP BY dow ORDER BY avg_views DESC LIMIT 1
        """).fetchone()

        sentiment_counts = db.execute("""
            SELECT sentiment, COUNT(*) as cnt FROM pub_comments GROUP BY sentiment
        """).fetchall()

        insights = []
        if views_change > 0:
            insights.append(f"Views grew {views_change}% this week vs prior period.")
        elif views_change < 0:
            insights.append(f"Views declined {views_change}% week-over-week.")
        else:
            insights.append("Not enough data for trend analysis yet.")

        if best and best[0]["views"] > 0:
            insights.append(f"Top content: \"{best[0]['title']}\" with {best[0]['views']} views.")

        if best_day:
            days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
            insights.append(f"Best posting day: {days[best_day['dow']]}.")

        sentiment_map = {r["sentiment"]: r["cnt"] for r in sentiment_counts}
        total_s = sum(sentiment_map.values())
        if total_s > 0:
            pos_pct = round(sentiment_map.get("positive", 0) / total_s * 100, 1)
            neg_pct = round(sentiment_map.get("negative", 0) / total_s * 100, 1)
            if pos_pct > 60:
                insights.append(f"Sentiment strongly positive ({pos_pct}%).")
            elif neg_pct > 20:
                insights.append(f"Negative sentiment at {neg_pct}%.")

        suggestions = []
        if views_change is not None and views_change < 10:
            suggestions.append("Try A/B testing different posting times.")
        if cur_views < 1000:
            suggestions.append("Increase posting frequency to build momentum.")
        suggestions.append("Monitor platform algorithm changes weekly.")
    finally:
        db.close()

    return jsonify({
        "insights": insights,
        "suggestions": suggestions,
        "metrics": {
            "views_change": views_change,
            "current_views": cur_views,
            "previous_views": prev_views,
            "best_day": dict(best_day) if best_day else None,
            "top_content": [dict(r) for r in best],
            "sentiment": {r["sentiment"]: r["cnt"] for r in sentiment_counts}
        }
    })


# ============================================================
# API: Reports
# ============================================================

@publishing_bp.route("/api/reports/generate", methods=["POST"])
def api_generate_report():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    data = request.json or {}
    period = data.get("period", "weekly")
    now = int(time.time())
    if period == "daily":
        start = now - 86400
        label = "Daily"
    elif period == "monthly":
        start = now - 86400 * 30
        label = "Monthly"
    else:
        start = now - 86400 * 7
        label = "Weekly"

    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        published = db.execute(
            "SELECT COUNT(*) FROM pub_schedules WHERE status='success' AND published_at>=?",
            (start,)).fetchone()[0]
        views = db.execute(
            "SELECT COALESCE(SUM(views),0) FROM pub_video_analytics WHERE date>=?",
            (start,)).fetchone()[0]
        likes = db.execute(
            "SELECT COALESCE(SUM(likes),0) FROM pub_video_analytics WHERE date>=?",
            (start,)).fetchone()[0]
        comments_ct = db.execute(
            "SELECT COALESCE(SUM(comments),0) FROM pub_video_analytics WHERE date>=?",
            (start,)).fetchone()[0]
        shares = db.execute(
            "SELECT COALESCE(SUM(shares),0) FROM pub_video_analytics WHERE date>=?",
            (start,)).fetchone()[0]
        engagement = likes + comments_ct + shares
        engagement_rate = round(engagement / views * 100, 2) if views > 0 else 0

        platforms = db.execute("""
            SELECT p.platform, SUM(a.views) as views, SUM(a.likes) as likes
            FROM pub_video_analytics a JOIN pub_platform_accounts p ON a.platform_account_id=p.id
            WHERE a.date>=? GROUP BY p.platform
        """, (start,)).fetchall()

        top = db.execute("""
            SELECT c.title, SUM(a.views) as views
            FROM pub_video_analytics a JOIN pub_content_items c ON a.content_item_id=c.id
            WHERE a.date>=? GROUP BY a.content_item_id ORDER BY views DESC LIMIT 5
        """, (start,)).fetchall()
    finally:
        db.close()

    return jsonify({
        "period": period, "label": label,
        "period_start": time.strftime("%Y-%m-%d", time.localtime(start)),
        "period_end": time.strftime("%Y-%m-%d", time.localtime(now)),
        "total_published": published, "total_views": views,
        "total_engagement": engagement, "engagement_rate": engagement_rate,
        "platforms": [dict(r) for r in platforms],
        "top_content": [dict(r) for r in top],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })


# ============================================================
# API: Production Schedule (Work Time)
# ============================================================

@publishing_bp.route("/api/production", methods=["GET"])
def api_list_production():
    date = request.args.get("date")
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        sql = "SELECT * FROM pub_production_schedule WHERE 1=1"
        params = []
        if date:
            sql += " AND date=?"
            params.append(date)
        sql += " ORDER BY date ASC, id ASC"
        rows = db.execute(sql, params).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])


@publishing_bp.route("/api/production", methods=["POST"])
def api_create_production():
    user_id = _login_required()
    if user_id is None:
        user_id = 0
    data = request.json or {}
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        c = db.execute("""INSERT INTO pub_production_schedule
            (user_id, date, task_type, duration_minutes, content_item_id, status, notes)
            VALUES (?,?,?,?,?,?,?)""",
            (user_id, data.get("date", ""), data.get("task_type", ""),
             int(data.get("duration_minutes", 60)), int(data.get("content_item_id", 0)),
             data.get("status", "planned"), data.get("notes", "")))
        db.commit()
        pk = c.lastrowid
    finally:
        db.close()
    return jsonify({"id": pk})


@publishing_bp.route("/api/production/<int:prod_id>", methods=["DELETE"])
def api_delete_production(prod_id):
    db = __import__("publishing_manager.db", fromlist=["get_db"]).get_db()
    try:
        db.execute("DELETE FROM pub_production_schedule WHERE id=?", (prod_id,))
        db.commit()
    finally:
        db.close()
    return jsonify({"ok": True})
