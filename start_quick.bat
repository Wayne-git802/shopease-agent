@echo off
chcp 65001 >nul
title ShopEase Agent - Quick Start
cd /d "%~dp0backend"

echo ========================================
echo   ShopEase Agent - Quick Start
echo ========================================
echo.

:: 1. Check MySQL
echo [1/3] Checking MySQL...
"%ProgramFiles%\MySQL\MySQL Server 8.4\bin\mysqladmin.exe" ping -h 127.0.0.1 -u root 2>nul >nul
if errorlevel 1 (
    echo   MySQL not running, starting...
    start "MySQL" /MIN "%ProgramFiles%\MySQL\MySQL Server 8.4\bin\mysqld.exe" --defaults-file=%USERPROFILE%\my.ini --console
    timeout /t 5 /nobreak >nul
    echo   MySQL started.
) else (
    echo   MySQL already running.
)

:: 2. Check venv
echo [2/3] Checking virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo   Creating venv...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt requests jinja2 numpy pydantic langgraph faiss-cpu sentence-transformers -q
)
echo   OK.

:: 3. Start Django
echo [3/3] Starting Django on http://127.0.0.1:8000/
echo.
start "ShopEase Django" .venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000

timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000/

echo Done! Keep this window open while working.
pause
