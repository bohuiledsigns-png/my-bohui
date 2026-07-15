#!/bin/bash
# ==========================================
# Deploy Rollback — 部署回滚
# 用法: bash scripts/deploy_rollback.sh [commit-hash]
# 默认回滚到 HEAD~1
# ==========================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [ROLLBACK] $*" | tee -a "$LOG_DIR/deploy.log"; }

cd "$APP_DIR"

TARGET="${1:-HEAD~1}"
log "Rolling back to $TARGET..."

# Stash any uncommitted changes
if ! git diff --quiet; then
    git stash push -m "auto-stash pre-rollback $(date '+%Y%m%d_%H%M%S')"
fi

# Checkout target
if git checkout "$TARGET" 2>&1; then
    log "Checked out $TARGET"
else
    log "ERROR: Checkout to $TARGET failed"
    exit 1
fi

# Restart Flask
log "Restarting Flask..."
PID_FILE="$APP_DIR/.crm_lock/app.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
fi

nohup python app.py >> "$APP_DIR/server_output.log" 2>&1 &
log "Flask started (PID $!)"

# Health check loop (up to 60 seconds)
for i in $(seq 1 12); do
    sleep 5
    if curl -sf http://127.0.0.1:5789/health > /dev/null 2>&1; then
        log "Health check PASSED after rollback"
        exit 0
    fi
    log "Waiting for health check... attempt $i"
done

log "WARNING: Health check failed after rollback — manual intervention required"
exit 1
