"""Background scheduler for video publishing."""
import threading
import time
import logging

logger = logging.getLogger(__name__)

_scheduler_thread = None
_scheduler_stop = threading.Event()


def start_scheduler(app, db_path):
    """Start the background scheduler thread."""
    global _scheduler_thread, _scheduler_stop
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[PublishScheduler] Already running")
        return _scheduler_thread, _scheduler_stop

    _scheduler_stop.clear()

    def _loop():
        with app.app_context():
            from .db import set_db_path
            set_db_path(db_path)
            logger.info("[PublishScheduler] Started (poll every 30s)")
            while not _scheduler_stop.is_set():
                try:
                    _process_queue(db_path)
                    _enqueue_due_schedules(db_path)
                    _cleanup_stale_locks(db_path)
                except Exception as e:
                    logger.error(f"[PublishScheduler] Error: {e}")
                _scheduler_stop.wait(30)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="pub-scheduler")
    _scheduler_thread.start()
    return _scheduler_thread, _scheduler_stop


def stop_scheduler():
    if _scheduler_stop:
        _scheduler_stop.set()


def _process_queue(db_path):
    """Process pending items in the publish queue."""
    from .db import get_db
    db = get_db()
    try:
        items = db.execute(
            "SELECT * FROM pub_publish_queue WHERE status='queued' ORDER BY id ASC LIMIT 3"
        ).fetchall()
        for item in items:
            db.execute(
                "UPDATE pub_publish_queue SET status='processing', locked_at=? WHERE id=?",
                (int(time.time()), item["id"])
            )
            db.commit()
            # Simulation: mark as published
            import random
            fake_post_id = f"sim_{item['id']}_{int(time.time())}"
            fake_url = f"https://example.com/video/{fake_post_id}"
            db.execute(
                "UPDATE pub_publish_queue SET status='success' WHERE id=?",
                (item["id"],)
            )
            db.execute(
                "UPDATE pub_schedules SET status='success', platform_post_id=?, platform_url=?, published_at=? WHERE id=?",
                (fake_post_id, fake_url, int(time.time()), item["schedule_id"])
            )
            db.commit()
            logger.info(f"[PublishScheduler] Simulated publish schedule#{item['schedule_id']}")
    finally:
        db.close()


def _enqueue_due_schedules(db_path):
    """Move due schedules to the publish queue."""
    from .db import get_db
    db = get_db()
    try:
        now = int(time.time())
        due = db.execute(
            """SELECT s.id FROM pub_schedules s
               WHERE s.status='pending' AND s.scheduled_at <= ?
               AND NOT EXISTS (SELECT 1 FROM pub_publish_queue q
                               WHERE q.schedule_id=s.id AND q.status IN ('queued','processing'))""",
            (now,)
        ).fetchall()
        for row in due:
            s = db.execute("SELECT * FROM pub_schedules WHERE id=?", (row["id"],)).fetchone()
            if not s:
                continue
            db.execute(
                "INSERT INTO pub_publish_queue (schedule_id, content_item_id, platform_account_id) VALUES (?,?,?)",
                (s["id"], s["content_item_id"], s["platform_account_id"])
            )
            db.commit()
            logger.info(f"[PublishScheduler] Enqueued schedule#{s['id']}")
    finally:
        db.close()


def _cleanup_stale_locks(db_path):
    """Release queue items stuck in 'processing' for over 5 minutes."""
    from .db import get_db
    db = get_db()
    try:
        stale_cutoff = int(time.time()) - 300
        db.execute(
            "UPDATE pub_publish_queue SET status='queued', locked_at=0 WHERE status='processing' AND locked_at > 0 AND locked_at < ?",
            (stale_cutoff,)
        )
        db.commit()
    finally:
        db.close()
