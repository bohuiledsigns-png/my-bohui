#!/bin/bash
# ==========================================
# DB Backup — WAL checkpoint + 备份 + 完整性校验
# 用法: bash scripts/db_backup.sh
# ==========================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$APP_DIR/crm_data.db"
BACKUP_DIR="$APP_DIR/backups"
LOG_DIR="$APP_DIR/logs"
TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/crm_data-${TIMESTAMP}.db"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

log() {
    local level="$1"
    shift
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*" >> "$LOG_DIR/backup.log"
}

log "INFO" "=== DB Backup Start ==="

# Phase A: WAL checkpoint
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>>"$LOG_DIR/backup.log"
    log "INFO" "WAL checkpoint done"
else
    log "ERROR" "Database not found: $DB_PATH"
    exit 1
fi

# Phase B: SHA256 checksum before backup
SUM_BEFORE=$(sha256sum "$DB_PATH" | awk '{print $1}')
log "INFO" "SHA256 before: $SUM_BEFORE"
SIZE=$(stat --printf="%s" "$DB_PATH" 2>/dev/null || stat -f%z "$DB_PATH" 2>/dev/null)
log "INFO" "DB size: $SIZE bytes"

# Phase C: Copy
cp "$DB_PATH" "$BACKUP_FILE"
log "INFO" "Copied to: $BACKUP_FILE"

# Verify copy
SUM_AFTER=$(sha256sum "$BACKUP_FILE" | awk '{print $1}')
if [ "$SUM_BEFORE" != "$SUM_AFTER" ]; then
    log "ERROR" "SHA256 mismatch! Backup corrupted."
    rm -f "$BACKUP_FILE"
    exit 1
fi
log "INFO" "SHA256 verified: $SUM_AFTER"

# Phase D: Integrity check
CHECK=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>&1)
if [ "$CHECK" != "ok" ]; then
    log "ERROR" "Integrity check failed: $CHECK"
    rm -f "$BACKUP_FILE"
    exit 1
fi
log "INFO" "Integrity check: ok"

# Phase E: Cleanup old backups (gzip >7 days, delete >30 days)
find "$BACKUP_DIR" -name "crm_data-*.db" -mtime +7 -not -name "*.gz" -exec gzip {} \; 2>/dev/null
log "INFO" "Gzipped backups older than 7 days"
find "$BACKUP_DIR" -name "crm_data-*.db.gz" -mtime +30 -delete 2>/dev/null
log "INFO" "Deleted backups older than 30 days"

log "INFO" "=== DB Backup Complete: ${TIMESTAMP} ==="
echo "$BACKUP_FILE"
