@echo off
cd /d "%~dp0"
cls
where py >nul 2>&1
if not errorlevel 1 (
    py -3 tablet_address.py
) else (
    python tablet_address.py
)
echo.
echo Press any key to close...
pause >nul
