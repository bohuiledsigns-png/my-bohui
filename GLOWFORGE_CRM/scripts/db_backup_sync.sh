#!/bin/bash
# ==========================================
# DB Backup Sync — 异地同步
# 通过 rclone 或 scp 将最新备份同步到远程
# 环境变量:
#   BACKUP_REMOTE_HOST   — 远程主机 (e.g., user@backup.example.com)
#   BACKUP_REMOTE_PATH   — 远程路径 (e.g., /backups/glowforge/)
#   BACKUP_SSH_KEY       — SSH 密钥路径 (可选)
#
# 未配置时静默跳过（优雅降级）
# ==========================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$APP_DIR/backups"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    shift
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" >> "$LOG_DIR/backup_sync.log"
}

REMOTE_HOST="${BACKUP_REMOTE_HOST:-}"
REMOTE_PATH="${BACKUP_REMOTE_PATH:-}"
SSH_KEY="${BACKUP_SSH_KEY:-}"

if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_PATH" ]; then
    log "INFO" "Remote backup not configured — skipping (set BACKUP_REMOTE_HOST and BACKUP_REMOTE_PATH)"
    exit 0
fi

# Find latest backup
LATEST=$(ls -t "$BACKUP_DIR"/crm_data-*.db 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    log "WARNING" "No backup files found to sync"
    exit 0
fi

log "INFO" "Syncing $(basename "$LATEST") to $REMOTE_HOST:$REMOTE_PATH"
LOCAL_SIZE=$(stat --printf="%s" "$LATEST" 2>/dev/null || stat -f%z "$LATEST" 2>/dev/null)

SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
[ -n "$SSH_KEY" ] && SSH_OPTS="$SSH_OPTS -i $SSH_KEY"

# Try rclone first, fall back to scp
if command -v rclone &>/dev/null; then
    # rclone scp-like copy
    rclone copy "$LATEST" ":scp:$REMOTE_HOST:$REMOTE_PATH" \
        --ssh-args="$SSH_OPTS" \
        --retries 3 \
        >> "$LOG_DIR/backup_sync.log" 2>&1
    log "INFO" "rclone sync: exit code $?"
else
    scp $SSH_OPTS "$LATEST" "${REMOTE_HOST}:${REMOTE_PATH}" \
        >> "$LOG_DIR/backup_sync.log" 2>&1
    log "INFO" "scp sync: exit code $?"
fi

# Verify remote size
REMOTE_SIZE=$(ssh $SSH_OPTS "$REMOTE_HOST" \
    "stat --printf='%s' '${REMOTE_PATH}/$(basename "$LATEST")' 2>/dev/null || echo 0" \
    2>/dev/null || echo 0)

if [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ]; then
    log "INFO" "Remote size verified: $REMOTE_SIZE bytes"
else
    log "WARNING" "Size mismatch: local=$LOCAL_SIZE remote=$REMOTE_SIZE"
fi

log "INFO" "=== Sync Complete ==="
