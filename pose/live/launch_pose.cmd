@echo off
setlocal
cd /d "%~dp0"
if exist "..\..\..\.venv\Scripts\python.exe" (
  "..\..\..\.venv\Scripts\python.exe" -B host\live_pose.py
) else (
  python -B host\live_pose.py
)
if errorlevel 1 pause
