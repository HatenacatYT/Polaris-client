@echo off
rem ASCII only on purpose (UTF-8 Japanese text breaks cmd.exe on Japanese Windows / cp932).
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=
if not exist .venv ( py -3 -m venv .venv || goto :fail )
.venv\Scripts\python -m pip install -r requirements-dev.txt || goto :fail
.venv\Scripts\python -m PyInstaller --noconfirm --clean polaris.spec || goto :fail
echo.
echo Done: dist\Polaris.exe  (single file)
echo For a faster-starting folder build run: build_exe_onedir.bat
pause
exit /b 0
:fail
echo.
echo Build FAILED. See the messages above.
pause
exit /b 1
