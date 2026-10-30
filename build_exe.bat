@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m PyInstaller --noconfirm --clean polaris.spec
echo.
echo 完成: dist\Polaris\Polaris.exe  （フォルダごと配布してください）
pause
