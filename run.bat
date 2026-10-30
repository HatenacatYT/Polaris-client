@echo off
rem ASCII only on purpose (UTF-8 Japanese text breaks cmd.exe on Japanese Windows / cp932).
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where py >nul 2>nul || ( echo Python 3.11 or later is required: https://www.python.org/ & pause & exit /b 1 )
if not exist .venv (
  echo First-time setup...
  py -3 -m venv .venv || ( echo Failed to create the virtual environment & pause & exit /b 1 )
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || ( echo Failed to install dependencies & pause & exit /b 1 )
)
start "" .venv\Scripts\pythonw.exe main.py
