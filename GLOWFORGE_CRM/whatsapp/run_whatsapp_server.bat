@echo off
chcp 65001 >nul
title GLOWFORGE WhatsApp 服务（自动重启）

:restart
echo [%date% %time%] 启动 WhatsApp 服务器...
python whatsapp_server.py
echo [%date% %time%] 服务器异常退出！10秒后重启...
echo [%date% %time%] 服务器异常退出 >> .whatsapp_session\restart.log
timeout /t 10 /nobreak >nul
goto restart
