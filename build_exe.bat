@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Checking Python 3.11...
py -3.11 --version
if errorlevel 1 goto error

echo [2/4] Installing dependencies...
py -3.11 -m pip install -r requirements-dev.txt
if errorlevel 1 goto error

echo [3/4] Installing PyInstaller...
py -3.11 -m pip install pyinstaller
if errorlevel 1 goto error

echo [4/4] Building Polaris...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

py -3.11 -m PyInstaller --noconfirm --clean --onefile --windowed --name Polaris --icon "polaris\assets\polaris.ico" --add-data "polaris\assets;polaris\assets" main.py
if errorlevel 1 goto error

echo.
echo SUCCESS: dist\Polaris.exe
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Check the error above.
pause
exit /b 1