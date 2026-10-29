@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Checking Python 3.11...
py -3.11 --version
if errorlevel 1 goto error
echo [2/3] Installing/updating dependencies for the current user...
py -3.11 -m pip install --user --upgrade -r requirements.txt
if errorlevel 1 goto error
echo [3/3] Starting Polaris...
py -3.11 main.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo Polaris could not start. Check the message above.
pause
exit /b 1
