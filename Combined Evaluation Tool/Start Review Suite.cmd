@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  echo First-time setup: py -3 -m venv .venv
  echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
)
pause
