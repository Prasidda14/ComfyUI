@echo off
rem Stops ComfyUI (port 8188) and the Video Studio page (port 8190). Frees the GPU/VRAM.
powershell -NoProfile -Command ^
  "foreach ($p in 8188,8190) {" ^
  "  $ids = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique;" ^
  "  if ($ids) { foreach ($i in $ids) { Stop-Process -Id $i -Force; Write-Host \"Stopped port $p (PID $i)\" } } else { Write-Host \"Port $p not running\" }" ^
  "}"
pause
