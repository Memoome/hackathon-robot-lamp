@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup-Windows.ps1 first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -B "apps\LJWB03-Lamp-Demo\visual_control.py"
