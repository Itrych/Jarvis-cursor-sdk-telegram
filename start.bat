@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv and install the package first.
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -e .
  exit /b 1
)
".venv\Scripts\python.exe" -m jarvis
