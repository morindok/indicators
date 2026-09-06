@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 digital_organism_2500.py chat-dashboard --internet --open-web --port 8051
) else (
    python digital_organism_2500.py chat-dashboard --internet --open-web --port 8051
)

echo.
echo Open http://127.0.0.1:8051 in your browser.
pause
endlocal
