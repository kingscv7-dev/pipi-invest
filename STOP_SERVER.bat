@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0stop_server.py" >nul 2>&1
    exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0stop_server.py" >nul 2>&1
    exit /b 0
)
exit /b 0
