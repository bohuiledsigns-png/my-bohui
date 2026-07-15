"""Multi-Platform Video Publishing Management System"""
import atexit
from flask import Blueprint

publishing_bp = Blueprint(
    'publishing', __name__,
    template_folder='../templates/publishing',
    static_folder='../static/publishing',
    static_url_path='/static/publishing'
)

_scheduler_thread = None
_scheduler_stop = None

from . import routes


def init_publishing(app, db_path):
    """Initialize publishing manager: database, scheduler, routes."""
    from .db import init_db
    init_db(db_path)

    # Scheduler 停用 — 当前只是模拟发布（fake_post_id），非实际功能
    global _scheduler_thread, _scheduler_stop
    _scheduler_thread = None
    _scheduler_stop = None

    app.register_blueprint(publishing_bp, url_prefix='/publishing')

    def _cleanup():
        pass
    atexit.register(_cleanup)
