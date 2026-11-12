@echo off
setlocal
echo ========================================================
echo Checking Docker Desktop status...
echo ========================================================

docker info >nul 2>&1
if errorlevel 1 goto :no_docker

echo Starting Odoo ERP and Local PostgreSQL database...
docker compose up -d
if errorlevel 1 goto :start_failed

echo.
echo ========================================================
echo [SUCCESS] Odoo ERP and Database are running!
echo URL: http://localhost:8069
echo ========================================================
echo.
echo Streaming live logs [Press Ctrl+C to stop following logs]:
docker compose logs -f odoo
goto :end

:no_docker
echo.
echo [ERROR] Docker Desktop is NOT running!
echo.
echo 1. Open Docker Desktop from your Start Menu or Desktop.
echo 2. Wait until Docker Desktop shows "Engine running".
echo 3. Once running, run start.bat again.
echo.
pause
goto :end

:start_failed
echo.
echo [ERROR] Failed to start containers. Check output above.
pause

:end
