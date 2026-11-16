@echo off
cd /d "%~dp0"
set "ESDP_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%ESDP_PYTHON%" (
  "%ESDP_PYTHON%" app.py
) else (
  py -3 app.py
)
pause
