#!/bin/bash
# ==========================================
# DB Integrity Check — 快速完整性探针
# 用于 CRON 每小时执行
# 检查: integrity, file size, modification time
# ==========================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$APP_DIR/crm_data.db"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    shift
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $*"
}

FAILURES=0

# 1. File exists
if [ ! -f "$DB_PATH" ]; then
    log "ERROR" "Database file missing: $DB_PATH"
    exit 1
fi

# 2. File size > 100KB
SIZE=$(stat --printf="%s" "$DB_PATH" 2>/dev/null || stat -f%z "$DB_PATH" 2>/dev/null)
if [ "$SIZE" -lt 102400 ]; then
    log "ERROR" "Database too small: $SIZE bytes"
    FAILURES=$((FAILURES + 1))
fi

# 3. Quick integrity check
CHECK=$(sqlite3 "$DB_PATH" "PRAGMA quick_check;" 2>&1)
if [ "$CHECK" != "ok" ]; then
    log "ERROR" "Integrity check failed: $CHECK"
    FAILURES=$((FAILURES + 1))
fi

# 4. Modification time within last 24 hours
MOD_TIME=$(stat --printf="%Y" "$DB_PATH" 2>/dev/null || stat -f%m "$DB_PATH" 2>/dev/null)
NOW=$(date +%s)
AGE=$(( (NOW - MOD_TIME) / 3600 ))
if [ "$AGE" -gt 25 ]; then
    log "WARNING" "DB not modified in $AGE hours (threshold: 24h)"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    log "INFO" "Integrity check: $FAILURES failure(s)"
    exit 1
else
    log "INFO" "Integrity check: ok (${SIZE} bytes, ${AGE}h since last mod)"
    exit 0
fi
