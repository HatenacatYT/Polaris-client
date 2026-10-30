@echo off
rem Folder build (starts faster than the single-file build). ASCII only on purpose.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set POLARIS_ONEDIR=1
if not exist .venv ( py -3 -m venv .venv || goto :fail )
.venv\Scripts\python -m pip install -r requirements-dev.txt || goto :fail
.venv\Scripts\python -m PyInstaller --noconfirm --clean polaris.spec || goto :fail
echo.
echo Done: dist\Polaris\Polaris.exe  (distribute the whole folder)
pause
exit /b 0
:fail
echo.
echo Build FAILED. See the messages above.
pause
exit /b 1
