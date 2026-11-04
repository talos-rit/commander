@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0commander-vision-integration\tools\Start-VisionConsole.ps1" -Restart -Background
if errorlevel 1 (
  echo Commander failed to start. See the error above.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8000"
exit /b 0
