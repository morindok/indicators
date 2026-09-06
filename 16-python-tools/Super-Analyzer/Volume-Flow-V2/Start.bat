@echo off
chcp 65001 >nul
title Morindok - Bybit Volume Flow Monitor
cd /d "%~dp0"
cls
echo ============================================================
echo   Morindok  -  Bybit Volume Flow Monitor
echo   Telegram: @BITMOON618
echo ============================================================
echo.

set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>nul && set "PYEXE=py"
)
if not defined PYEXE (
    echo [خطا] پایتون روی این سیستم پیدا نشد.
    echo.
    echo لطفاً ابتدا پایتون را از آدرس زیر نصب کنید:
    echo    https://www.python.org/downloads/
    echo هنگام نصب حتماً تیک "Add python.exe to PATH" را بزنید،
    echo سپس دوباره همین فایل را اجرا کنید.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] در حال ساخت محیط مجازی پایتون ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo [خطا] ساخت محیط مجازی ناموفق بود.
        pause
        exit /b 1
    )
)

echo [2/3] در حال بررسی و نصب کتابخانه‌های مورد نیاز ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [خطا] نصب کتابخانه‌ها ناموفق بود. اتصال اینترنت خود را بررسی کنید.
    pause
    exit /b 1
)

echo [3/3] در حال اجرای برنامه ...
echo.
echo مرورگر به صورت خودکار باز می‌شود.
echo آدرس دستی در صورت نیاز:  http://127.0.0.1:8050
echo برای خاموش‌کردن برنامه، همین پنجره سیاه را ببندید.
echo.

start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8050"
".venv\Scripts\python.exe" app.py

echo.
echo برنامه متوقف شد.
pause
