@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Stop ShopEase

echo Stopping ShopEase servers on ports 8000 and 5173...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do taskkill /F /PID %%P >nul 2>nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173 .*LISTENING"') do taskkill /F /PID %%P >nul 2>nul

echo Done.
pause
