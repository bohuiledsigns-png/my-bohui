#!/bin/bash
# ==========================================
# Deploy Check — 部署前预检
# 在 deploy.sh 开始时执行，失败则阻止部署
# ==========================================
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [DEPLOY-CHECK] $*"
}

FAILURES=0

cd "$APP_DIR"

# 1. 分支检查：只允许 main/master
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
    log "ERROR: 当前分支 '$BRANCH' 不是 main/master。仅允许主分支部署。"
    FAILURES=$((FAILURES + 1))
fi

# 2. Python 语法检查
PY_FILES=$(git diff --name-only HEAD 2>/dev/null || find "$APP_DIR" -name "*.py" -not -path "*/__pycache__/*" -not -path "*/\.*")
for f in $PY_FILES; do
    if [ -f "$f" ]; then
        if ! python -m py_compile "$f" 2>> "$LOG_DIR/deploy_check.log"; then
            log "ERROR: Python 语法错误: $f"
            FAILURES=$((FAILURES + 1))
        fi
    fi
done

# 3. 磁盘空间 > 20%
if command -v df &>/dev/null; then
    AVAIL_PCT=$(df --output=pcent "$APP_DIR" 2>/dev/null | tail -1 | tr -d ' %' || echo 0)
    if [ "$AVAIL_PCT" -gt 80 ]; then
        log "ERROR: 磁盘使用率 ${AVAIL_PCT}%，超过 80% 阈值"
        FAILURES=$((FAILURES + 1))
    fi
fi

# 4. DB 完整性
DB_PATH="$APP_DIR/crm_data.db"
if [ -f "$DB_PATH" ]; then
    if command -v sqlite3 &>/dev/null; then
        CHECK=$(sqlite3 "$DB_PATH" "PRAGMA quick_check;" 2>&1)
        if [ "$CHECK" != "ok" ]; then
            log "ERROR: 数据库完整性检查失败"
            FAILURES=$((FAILURES + 1))
        fi
    fi
else
    log "WARNING: 数据库文件不存在（新部署可忽略）"
fi

# 5. WhatsApp 服务可达
if command -v curl &>/dev/null; then
    if ! curl -sf http://127.0.0.1:15789/health > /dev/null 2>&1; then
        log "WARNING: WhatsApp 服务 (15789) 不可达 —— 部署后需手动检查"
        # Not a hard failure — WhatsApp might be legitimately down during deploy
    fi
fi

if [ "$FAILURES" -gt 0 ]; then
    log "FAILED: $FAILURES 项检查未通过，终止部署"
    exit 1
else
    log "PASSED: 全部检查通过"
    exit 0
fi
