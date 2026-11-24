@echo off
rem Starts ComfyUI from this repo. Open http://127.0.0.1:8188 in the browser.
rem ffmpeg for LatentSync / video nodes (bundled in tools\bin)
set "PATH=%~dp0tools\bin;%PATH%"
cd /d "%~dp0ComfyUI_windows_portable"
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --extra-model-paths-config "%~dp0extra_model_paths.yaml" --output-directory "%~dp0ComfyUI_windows_portable\ComfyUI\output" --preview-method auto %*
pause
