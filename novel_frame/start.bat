@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "VENV=%ROOT%backend\.venv"
set "CONFIG=%ROOT%config.json"

echo ============================================
echo   AI Novel Agent - Unified Launcher
echo ============================================
echo.

:: ---- Check config.json ----
if not exist "%CONFIG%" (
    echo [ERROR] config.json not found.
    echo         Copying config.example.json ...
    if exist "%ROOT%config.example.json" (
        copy "%ROOT%config.example.json" "%CONFIG%" >nul
        echo         Done. Please edit config.json to fill in your API key, then re-run.
    ) else (
        echo         config.example.json also missing. Please create config.json manually.
    )
    pause
    exit /b 1
)

:: ---- Parse ports from config.json via Python one-liner ----
for /f %%a in ('python -c "import json;c=json.load(open(r'%CONFIG%'));print(c.get('server',{}).get('backend_port',8000))"') do set "BACKEND_PORT=%%a"
for /f %%a in ('python -c "import json;c=json.load(open(r'%CONFIG%'));print(c.get('server',{}).get('frontend_port',3000))"') do set "FRONTEND_PORT=%%a"

echo [Config] Backend port : %BACKEND_PORT%
echo [Config] Frontend port: %FRONTEND_PORT%
echo.

:: ---- Setup Python venv ----
if not exist "%VENV%\Scripts\activate.bat" (
    echo [Step 1/4] Creating Python virtual environment ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Is Python installed and in PATH?
        pause
        exit /b 1
    )
    echo           venv created at %VENV%
) else (
    echo [Step 1/4] Python venv already exists.
)

:: ---- Install Python dependencies ----
echo [Step 2/4] Installing Python dependencies ...
call "%VENV%\Scripts\activate.bat"
pip install -r "%ROOT%backend\requirements.txt" -q
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
echo           Dependencies installed.
echo.

:: ---- Install Node.js dependencies ----
echo [Step 3/4] Installing Node.js dependencies ...
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Is Node.js installed and in PATH?
        pause
        exit /b 1
    )
) else (
    echo           node_modules already exists, skipping.
)
echo.

:: ---- Launch both services ----
echo [Step 4/4] Starting services ...
echo.
echo   Backend  : http://localhost:%BACKEND_PORT%
echo   Frontend : http://localhost:%FRONTEND_PORT%
echo.
echo   Press Ctrl+C in either window to stop.
echo ============================================

:: Start backend in a new window
start "Novel-Agent Backend" cmd /k "cd /d "%ROOT%backend" && call "%VENV%\Scripts\activate.bat" && python main.py"

:: Wait briefly for backend to initialize, then open browser
timeout /t 3 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%"

:: Start frontend in this window (keeps script alive)
cd /d "%ROOT%frontend"
set "BACKEND_PORT=%BACKEND_PORT%"
set "FRONTEND_PORT=%FRONTEND_PORT%"
call npx vite --port %FRONTEND_PORT%
