@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (echo [ERROR] Python virtual environment not found at "%~dp0.venv\Scripts\python.exe" & pause & exit /b 1)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\odoo_ctl.py" load %*
exit /b %errorlevel%
