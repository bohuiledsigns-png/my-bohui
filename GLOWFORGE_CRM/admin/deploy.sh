#!/bin/bash
# ==========================================
# Safe Deploy — 安全部署脚本（在服务器上执行）
# ==========================================
# 用法:
#   ssh root@server 'bash -s' < deploy.sh
#   或在服务器上直接: bash deploy.sh
# ==========================================
set -e

APP_DIR="/www/wwwroot/GLOWFORGE_CRM"
LOG_FILE="/tmp/glowforge_deploy.log"
BACKUP_DIR="/www/backups/deploy"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Deploy Start ===" | tee -a "$LOG_FILE"

cd "$APP_DIR" || { echo "ERROR: $APP_DIR not found"; exit 1; }

# V0-SAFETY: Pre-deployment checks
echo "[PREFLIGHT] Running deploy checks..." | tee -a "$LOG_FILE"
if bash scripts/deploy_check.sh >> "$LOG_FILE" 2>&1; then
    echo "  Preflight checks PASSED" | tee -a "$LOG_FILE"
else
    echo "  ERROR: Preflight checks failed. Aborting deploy." | tee -a "$LOG_FILE"
    exit 1
fi

# 0. V0-SAFETY: Pre-deploy database backup
echo "[0/6] Backing up database..." | tee -a "$LOG_FILE"
bash scripts/db_backup.sh >> "$LOG_FILE" 2>&1
echo "  DB backup done" | tee -a "$LOG_FILE"

# 1. 记录部署前状态
echo "[1/6] Recording pre-deploy state..." | tee -a "$LOG_FILE"
git log --oneline -3 > /tmp/pre_deploy_log.txt
PRE_HASH=$(git rev-parse HEAD)

# 2. 检查是否有未提交的修改
echo "[2/6] Checking working tree..." | tee -a "$LOG_FILE"
if ! git diff --quiet; then
    echo "  WARNING: Uncommitted changes found. Stashing..." | tee -a "$LOG_FILE"
    git stash push -m "auto-stash pre-deploy $(date '+%Y%m%d_%H%M%S')"
fi

# 3. 安全拉取
echo "[3/6] Pulling latest..." | tee -a "$LOG_FILE"
git fetch origin 2>&1 | tee -a "$LOG_FILE"

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse @{upstream})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "  Already up to date (${LOCAL:0:8})" | tee -a "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Deploy: No Update ===" | tee -a "$LOG_FILE"
    exit 0
fi

echo "  Local:  ${LOCAL:0:8}" | tee -a "$LOG_FILE"
echo "  Remote: ${REMOTE:0:8}" | tee -a "$LOG_FILE"

# 尝试 fast-forward merge (安全)
if git merge --ff-only "$REMOTE" 2>&1; then
    echo "  Fast-forward merge OK" | tee -a "$LOG_FILE"
else
    echo "  ERROR: Fast-forward merge failed. Resolve conflicts manually." | tee -a "$LOG_FILE"
    echo "  Commands: git merge --abort | git rebase --abort" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. 验证部署
echo "[4/6] Validating..." | tee -a "$LOG_FILE"
git log --oneline -3
NEW_HASH=$(git rev-parse HEAD)
echo "  ${PRE_HASH:0:8} → ${NEW_HASH:0:8}" | tee -a "$LOG_FILE"

# 5. 重启服务
echo "[5/6] Restarting services..." | tee -a "$LOG_FILE"
cd "$APP_DIR"

# 杀掉旧 Flask 进程
PID_FILE=".crm_lock/app.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  Stopping Flask (PID $OLD_PID)..." | tee -a "$LOG_FILE"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
fi

# 重启 Flask
echo "  Starting Flask..." | tee -a "$LOG_FILE"
nohup python app.py >> server_output.log 2>&1 &
echo "  Flask started (PID $!)" | tee -a "$LOG_FILE"

# 等待启动
echo "  Waiting for health check..." | tee -a "$LOG_FILE"
HEALTH_PASSED=false
for i in $(seq 1 6); do
    sleep 5
    if curl -sf http://127.0.0.1:5789/health > /dev/null 2>&1; then
        HEALTH_PASSED=true
        break
    fi
    echo "  Health check attempt $i/6..." | tee -a "$LOG_FILE"
done

if [ "$HEALTH_PASSED" = true ]; then
    echo "  Health check PASSED" | tee -a "$LOG_FILE"
else
    echo "  WARNING: Health check failed — triggering rollback..." | tee -a "$LOG_FILE"
    bash scripts/deploy_rollback.sh "$PRE_HASH" >> "$LOG_FILE" 2>&1
    echo "  Rollback to $PRE_HASH completed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[6/6] Deploy log written" | tee -a "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === Deploy Complete (${PRE_HASH:0:8} → ${NEW_HASH:0:8}) ===" | tee -a "$LOG_FILE"
