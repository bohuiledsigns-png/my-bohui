@echo off
chcp 65001 >nul
title GLOWFORGE 一键启动
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ========================================
echo   GLOWFORGE CRM 一键启动
echo   自动启动 WhatsApp + CRM + 浏览器
echo ========================================
echo.
echo [%time%] 清理旧进程...

:: 1. 杀掉旧进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5789" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":15789" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: 2. 清理锁文件
if exist ".crm_lock\app.pid" del ".crm_lock\app.pid" 2>nul
if exist ".crm_lock\app.lock" del ".crm_lock\app.lock" 2>nul

:: 3. 启动 WhatsApp 服务（后台最小化窗口）
echo [%time%] 启动 WhatsApp 服务...
start "GLOWFORGE WhatsApp" /MIN cmd /c run_whatsapp_server.bat
echo   等待服务就绪...

:: 4. 等待 WhatsApp 健康检查（最多30秒）
set WA_READY=0
for /l %%i in (1,1,15) do (
    powershell -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:15789/health' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
    if !errorlevel! equ 0 (
        set WA_READY=1
        goto :wa_ok
    )
    timeout /t 2 /nobreak >nul
)
:wa_ok
if %WA_READY% equ 1 (
    echo    [OK] WhatsApp 服务已就绪 ^(端口 15789^)
) else (
    echo    [!] WhatsApp 未就绪 ^(继续启动CRM^)
)

:: 5. 启动 CRM 服务器（后台最小化窗口）
echo [%time%] 启动 CRM 服务器...
start "GLOWFORGE CRM" /MIN cmd /c python app.py
echo   等待 CRM 就绪...

:: 6. 等待 CRM 就绪（最多30秒）
set CRM_READY=0
for /l %%i in (1,1,15) do (
    powershell -Command "try{$r=Invoke-WebRequest 'http://localhost:5789' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
    if !errorlevel! equ 0 (
        set CRM_READY=1
        goto :crm_ok
    )
    timeout /t 2 /nobreak >nul
)
:crm_ok
if %CRM_READY% equ 1 (
    echo    [OK] CRM 已就绪 ^(端口 5789^)
) else (
    echo    [!] CRM 启动超时，继续打开浏览器...
)

:: 7. 打开浏览器
echo.
echo ========================================
echo   GLOWFORGE CRM 启动完成！
echo.
echo   CRM:      http://localhost:5789
echo   WhatsApp: http://127.0.0.1:15789
echo ========================================
echo.
start http://localhost:5789
echo [%time%] 浏览器已打开
echo.
echo 提示：
echo   - WhatsApp 窗口会弹出 Chrome 浏览器
echo   - 首次需要手机扫码登录（之后自动记住）
echo   - 如果 Chrome 闪退，WhatsApp 服务会自动重启
echo   - 关闭此窗口不影响后台运行的服务
echo.

:: 8. 写入启动日志
echo [%date% %time%] 一键启动 >> .whatsapp_session\startup.log 2>nul

:: 保持窗口打开，显示实时状态
echo 正在监控 WhatsApp 状态（按 Ctrl+C 退出监控）...
echo.

:monitor
timeout /t 30 /nobreak >nul
powershell -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:15789/health' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200){write-host '  [OK] WhatsApp 运行中' -f Green}else{write-host '  [!] WhatsApp 离线' -f Red}}catch{write-host '  [!] WhatsApp 离线' -f Red}" 2>nul
goto monitor
