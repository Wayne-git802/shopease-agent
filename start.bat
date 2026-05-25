@echo off
setlocal EnableExtensions
chcp 65001 >nul
title ShopEase One-Click Launcher

cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:5173/"

echo ========================================
echo   ShopEase One-Click Launcher
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found. Please install Python 3.10 or newer.
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found. Please install Node.js 18 or newer.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found. Please reinstall Node.js.
  pause
  exit /b 1
)

echo [1/7] Stopping old ShopEase servers on ports 8000 and 5173...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do taskkill /F /PID %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173 .*LISTENING"') do taskkill /F /PID %%P >nul 2>nul

echo [2/7] Checking Python virtual environment...
if exist "%PYTHON%" (
  "%PYTHON%" --version >nul 2>nul
  if errorlevel 1 (
    echo Existing virtual environment is not usable. Recreating it...
    rmdir /s /q "%BACKEND%\.venv"
  )
)

if not exist "%PYTHON%" (
  echo Creating virtual environment...
  python -m venv "%BACKEND%\.venv"
  if errorlevel 1 (
    echo [ERROR] Failed to create Python virtual environment.
    pause
    exit /b 1
  )
)

echo [3/7] Installing backend dependencies...
cd /d "%BACKEND%"
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :backend_error
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :backend_error

echo [4/7] Migrating database and installing data...
"%PYTHON%" manage.py migrate --noinput
if errorlevel 1 goto :backend_error
"%PYTHON%" ..\scripts\data\ensure_data.py
if errorlevel 1 goto :backend_error

echo [5/7] Installing frontend dependencies...
cd /d "%FRONTEND%"
call npm install
if errorlevel 1 (
  echo [ERROR] Frontend dependency installation failed.
  pause
  exit /b 1
)

echo [6/7] Starting backend and frontend servers...
start "ShopEase Backend" /D "%BACKEND%" cmd /k ..\scripts\server\start_server.bat
timeout /t 2 /nobreak >nul
start "ShopEase Frontend" /D "%FRONTEND%" cmd /k RUN_FRONTEND_SERVER.bat

echo [7/7] Waiting for the website, then opening browser...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%URL%'; for($i=0; $i -lt 40; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; if($r.StatusCode -lt 500){ Start-Process $url; exit 0 } } catch { Start-Sleep -Seconds 1 } }; Start-Process $url"

echo.
echo ShopEase is starting at %URL%
echo Backend:  http://127.0.0.1:8000/
echo Frontend: %URL%
echo.
echo Demo accounts:
echo   Admin:    admin / admin123
echo   Customer: c00001 / gi6AWCRM7fLh
echo   Seller:   s00001 / pZ9R9a%%jcqhW
echo   CSV Admin: a00001 / HF2z8n#xytDp
echo.
echo You can close this launcher window. Keep the Backend and Frontend windows open while using the site.
pause
exit /b 0

:backend_error
echo [ERROR] Backend setup failed. Please read the message above.
pause
exit /b 1
