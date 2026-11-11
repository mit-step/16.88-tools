@echo off
cd /d "%~dp0"
set "PDR_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PDR_PYTHON%" (
  echo Bundled Python not found. Install requirements.txt and run: python workspace_app.py
  pause
  exit /b 1
)
echo Starting your PDR feedback workspace at http://127.0.0.1:8765
echo Leave this window open while using the workspace. Ctrl+C stops it.
"%PDR_PYTHON%" workspace_app.py
pause
