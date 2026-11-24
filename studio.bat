@echo off
rem Video Studio: starts ComfyUI (if not already running) + the Studio page, then opens the browser.
cd /d "%~dp0"
powershell -NoProfile -Command "try { Invoke-WebRequest http://127.0.0.1:8188/system_stats -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Starting ComfyUI in its own window - takes ~20-30s...
  start "ComfyUI" /d "%~dp0" cmd.exe /c "%~dp0start_comfyui.bat"
)
start "" http://127.0.0.1:8190
"%~dp0ComfyUI_windows_portable\python_embeded\python.exe" -s "%~dp0tools\studio.py"
pause
