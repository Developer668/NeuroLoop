@echo off
cd /d "%~dp0"
"%~dp0.runtimes\app\Scripts\python.exe" "%~dp0scripts\manage.py" serve
if errorlevel 1 pause
