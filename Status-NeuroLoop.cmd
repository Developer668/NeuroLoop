@echo off
cd /d "%~dp0"
"%~dp0.runtimes\app\Scripts\python.exe" "%~dp0scripts\manage.py" status
pause
