@echo off
cd /d "%~dp0"
title MAKEMYDRUMKIT
echo ============================================
echo   MAKEMYDRUMKIT
echo   by LOSTINLIMERENCE
echo ============================================
echo.

python --version >nul 2>nul
if errorlevel 1 (
    echo Python isn't installed on this computer yet.
    echo.
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Run the installer
    echo   3. IMPORTANT: on the first install screen, check the box
    echo      that says "Add python.exe to PATH" before clicking Install
    echo   4. Once it finishes, double-click this file again
    echo.
    pause
    exit /b 1
)

echo Checking requirements — first run only, takes a minute or two...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo Something went wrong installing requirements. Scroll up to see the
    echo error, or ask whoever gave you this for help.
    echo.
    pause
    exit /b 1
)

python run_server.py

echo.
echo App stopped. You can close this window.
pause
