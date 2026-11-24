@echo off
rem Renders all shots of a project through the running ComfyUI.
rem   run_shots.bat projects\example
rem   run_shots.bat projects\example --preset realism --only s01
rem   run_shots.bat projects\example --seeds 4          (draft seed sweep)
"%~dp0ComfyUI_windows_portable\python_embeded\python.exe" "%~dp0tools\shots.py" %*
