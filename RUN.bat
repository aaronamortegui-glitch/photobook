@echo off
rem Starts QwenStudio if it is not running (config.json), then Photobook, and opens it.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo   The environment is missing. Run INSTALL.bat first.
  pause
  exit /b 1
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m photobook.lanzar
pause
