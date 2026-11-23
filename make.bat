@echo off
rem Full pipeline: reference image -> video -> voice + lip sync -> sound -> final.mp4
rem   make.bat jobs\my_job        (edit jobs\my_job\job.txt first)
rem New job: copy jobs\_template to jobs\<name> and edit job.txt
"%~dp0ComfyUI_windows_portable\python_embeded\python.exe" -s "%~dp0tools\make.py" %*
