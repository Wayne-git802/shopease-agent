@echo off
cd /d C:\Users\admin\Desktop\shop_agent\backend

echo ================================
echo   ShopEase Server Manager
echo ================================
echo.

echo [1/3] Stopping old server processes...
:: Kill anything on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo   Killing PID %%a (port 8000)
    taskkill /F /PID %%a 2>nul
)
:: Kill any existing ShopEase server window
taskkill /FI "WINDOWTITLE eq ShopEase*" /F 2>nul

:: Wait 2 seconds (ping trick - works in both cmd and git-bash)
ping -n 3 127.0.0.1 >nul

echo [2/3] Starting Django server...
start "ShopEase Server" D:\Python\python.exe manage.py runserver 127.0.0.1:8000

:: Wait for startup
ping -n 4 127.0.0.1 >nul

echo [3/3] Server should be ready!
echo.
echo   >>  http://127.0.0.1:8000/
echo.
echo Close the SERVER window to stop, or this window to exit.
pause
