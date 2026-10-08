@echo off
cd /d "%~dp0"
cls
where py >nul 2>&1
if not errorlevel 1 (
    py -3 tablet_check.py
) else (
    python tablet_check.py
)
echo.
echo Press any key to close...
pause >nul
