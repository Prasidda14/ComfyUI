@echo off
rem Builds the project dependency graph (graph.json) and prints summary.
rem   graphify.bat
rem   graphify.bat --open
rem   graphify.bat --out custom.json
"%~dp0ComfyUI_windows_portable\python_embeded\python.exe" -s "%~dp0tools\graphify.py" %*
