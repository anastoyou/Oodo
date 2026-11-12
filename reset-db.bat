@echo off
setlocal
echo ========================================================
echo WARNING: This will completely erase all databases and data!
echo ========================================================
set /p CONFIRM="Are you sure you want to completely clear the database? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo Operation cancelled.
    pause
    exit /b
)

echo Stopping containers and removing all database volumes...
docker compose down -v
echo.
echo Starting fresh containers...
docker compose up -d
echo.
echo ========================================================
echo Database has been completely cleared!
echo Open http://localhost:8069 to create your new fresh database.
echo ========================================================
pause

