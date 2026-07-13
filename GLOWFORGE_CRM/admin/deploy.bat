@echo off
chcp 65001 >nul
title GLOWFORGE CRM - Deploy to Server

echo ========================================
echo   Deploy GLOWFORGE CRM to Production
echo ========================================
echo.

cd /d "%~dp0"

:: 1. Show current status
echo [1/4] Checking git status...
git status --short
echo.

:: 2. Push to server
echo [2/4] Pushing to server...
git push origin HEAD
if %errorlevel% neq 0 (
    echo ERROR: Push failed!
    pause
    exit /b 1
)
echo   Push OK
echo.

:: 3. SSH to server and run deploy
echo [3/4] Running deploy on server...
echo.
ssh root@47.243.63.197 "cd /www/wwwroot/GLOWFORGE_CRM && bash deploy.sh" < nul
echo.

:: 4. Verify
echo [4/4] Verifying deployment...
timeout /t 5 /nobreak >nul
curl -s http://47.243.63.197:5789/health 2>nul && echo. || echo WARNING: Health check endpoint not available yet

echo.
echo ========================================
echo   Deploy Complete!
echo ========================================
echo.
pause
