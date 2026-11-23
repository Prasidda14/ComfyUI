@echo off
rem Photoreal stills (Z-Image Turbo) for a project's refs folder.
rem   run_image.bat projects\example "sitting at a cafe table holding a coffee cup" --count 4
"%~dp0ComfyUI_windows_portable\python_embeded\python.exe" "%~dp0tools\image.py" %*
