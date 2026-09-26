@echo off
setlocal
cd /d "%~dp0"

echo ==================================================================
echo   Photobook - installer
echo ==================================================================
echo.
echo   Nothing on your system is touched: uv downloads its own Python
echo   and the environment lives inside this folder (about 1 GB with
echo   the models). QwenStudio must be installed separately.
echo.

set "UVDIR=%~dp0.uv"
set "UV=%UVDIR%\uv.exe"

if not exist "%UV%" (
  echo   Downloading uv...
  if not exist "%UVDIR%" mkdir "%UVDIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$u='https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip';" ^
    "$z=Join-Path $env:TEMP 'uv.zip';" ^
    "Invoke-WebRequest -Uri $u -OutFile $z -UseBasicParsing;" ^
    "Expand-Archive -Path $z -DestinationPath '%UVDIR%' -Force;" ^
    "Remove-Item $z -Force"
  if errorlevel 1 (
    echo.
    echo   Could not download uv. Check your internet connection.
    pause
    exit /b 1
  )
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo   Creating an isolated environment with Python 3.12...
  "%UV%" venv "%~dp0.venv" --python 3.12
  if errorlevel 1 (
    echo.
    echo   Could not create the environment.
    pause
    exit /b 1
  )
)

echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0instalar.py"
if errorlevel 1 (
  echo.
  echo   The install did not finish cleanly.
  pause
  exit /b 1
)

call "%~dp0SHORTCUT.bat" quiet >nul 2>&1
if exist "%USERPROFILE%\Desktop\Photobook.lnk" echo   Photobook is on your desktop.
echo.
pause
