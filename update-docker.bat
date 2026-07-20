@echo off
setlocal EnableExtensions EnableDelayedExpansion

if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help

set "PROJECT_ROOT=%~dp0"
set "COMPOSE_FILE=%PROJECT_ROOT%deploy\docker\docker-compose.yml"
set "ENV_FILE=%PROJECT_ROOT%.env"
set "COMPOSE_SERVICES=backend"
set "CHECK_ONLY="

if /I "%~1"=="--all" (
    set "COMPOSE_SERVICES="
) else if /I "%~1"=="--backend-only" (
    set "COMPOSE_SERVICES=backend"
) else if /I "%~1"=="--check" (
    set "CHECK_ONLY=1"
) else if not "%~1"=="" (
    echo [ERROR] Unknown option: %~1
    echo.
    goto :help_error
)

pushd "%PROJECT_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot enter project directory: %PROJECT_ROOT%
    exit /b 1
)

echo [1/5] Checking Docker and deployment files...
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI was not found. Install or start Docker Desktop first.
    goto :fail
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Compose v2 is unavailable. Update Docker Desktop first.
    goto :fail
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running or the daemon is unreachable.
    goto :fail
)

if not exist "%COMPOSE_FILE%" (
    echo [ERROR] Missing Compose file: %COMPOSE_FILE%
    goto :fail
)

if not exist "%ENV_FILE%" (
    echo [ERROR] Missing .env. Copy .env.example to .env and configure it first.
    goto :fail
)

if not exist "%PROJECT_ROOT%config.json" (
    echo [ERROR] Missing config.json required by the Docker bind mount.
    goto :fail
)

echo [2/5] Validating Docker Compose configuration...
docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" config --quiet
if errorlevel 1 (
    echo [ERROR] Compose validation failed. Existing containers were not changed.
    goto :fail
)
if defined CHECK_ONLY goto :check_success

echo [3/5] Building the latest local source and recreating services...
if defined COMPOSE_SERVICES (
    docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" up -d --build !COMPOSE_SERVICES!
) else (
    docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" up -d --build --remove-orphans
)
if errorlevel 1 (
    echo [ERROR] Build or deployment failed. Check the output above.
    goto :fail
)

echo [4/5] Locating the backend container...
set "BACKEND_ID="
for /f "delims=" %%I in ('docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" ps -q backend') do set "BACKEND_ID=%%I"
if not defined BACKEND_ID (
    echo [ERROR] The backend container was not created.
    goto :show_logs
)

echo [5/5] Waiting for backend health ^(up to 5 minutes^)...
set /a HEALTH_ATTEMPT=0

:wait_health
set /a HEALTH_ATTEMPT+=1
set "BACKEND_HEALTH="
for /f "delims=" %%H in ('docker inspect --format "{{.State.Health.Status}}" "!BACKEND_ID!" 2^>nul') do set "BACKEND_HEALTH=%%H"

if /I "!BACKEND_HEALTH!"=="healthy" goto :success
if not defined BACKEND_HEALTH set "BACKEND_HEALTH=starting"
echo        Attempt !HEALTH_ATTEMPT!/60: !BACKEND_HEALTH!

if !HEALTH_ATTEMPT! GEQ 60 goto :health_timeout
timeout /t 5 /nobreak >nul
goto :wait_health

:success
echo.
echo [OK] Docker deployment updated successfully.
docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" ps
echo.
echo Backend health endpoint: http://127.0.0.1:8762/api/health
popd >nul
exit /b 0

:check_success
echo.
echo [OK] Docker, required files, and Compose configuration are ready.
echo No containers were changed.
popd >nul
exit /b 0

:health_timeout
echo [ERROR] Backend did not become healthy within 5 minutes.

:show_logs
echo.
echo Last 100 backend log lines:
docker compose -f "%COMPOSE_FILE%" --env-file "%ENV_FILE%" logs --tail 100 backend

:fail
echo.
echo [FAILED] Existing data under data\ was not removed.
popd >nul
exit /b 1

:help
echo Usage: update-docker.bat [--all ^| --backend-only ^| --check]
echo.
echo Rebuild the current local source and update the existing Windows Docker
echo Compose deployment. The script does not pull Git changes, delete data,
echo prune images, or rewrite configuration files.
echo.
echo Options:
echo   --all            Reconcile backend and Cloudflare Tunnel services.
echo   --backend-only   Rebuild only backend ^(default; keeps Tunnel state^).
echo   --check          Validate prerequisites without changing containers.
echo   --help, /?       Show this help.
exit /b 0

:help_error
echo Usage: update-docker.bat [--all ^| --backend-only ^| --check]
exit /b 2
