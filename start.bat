@echo off
REM 启动后端 + 前端 dev 服务器(两个独立窗口)
REM 后端: http://127.0.0.1:8762  前端: http://127.0.0.1:3143/

chcp 65001 >nul

set ROOT=%~dp0
cd /d "%ROOT%"

start "novel-auto backend (FastAPI)" cmd /k "python run.py --reload"
start "novel-auto frontend (Vite)" cmd /k "cd frontend && npm run dev"

echo.
echo Backend → http://127.0.0.1:8762
echo Frontend → http://127.0.0.1:3143/
echo.
