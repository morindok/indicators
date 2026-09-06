@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 digital_organism_2500.py chat --internet --trace
) else (
    python digital_organism_2500.py chat --internet --trace
)

echo.
pause
endlocal
