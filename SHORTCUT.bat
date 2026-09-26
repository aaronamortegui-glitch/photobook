@echo off
rem A desktop shortcut with Photobook's icon (a .bat cannot carry one; a .lnk can).
set "APP=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Photobook.lnk');" ^
  "$s.TargetPath='%APP%RUN.bat'; $s.WorkingDirectory='%APP%'; $s.IconLocation='%APP%photobook\web\photobook.ico';" ^
  "$s.WindowStyle=7; $s.Save()"
if not "%~1"=="quiet" echo   Shortcut created on the desktop.
