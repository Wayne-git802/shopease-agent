@echo off
cd /d "%~dp0..\..\backend"
echo Starting Django Server...
..\..\.venv\Scripts\python.exe manage.py runserver
pause
