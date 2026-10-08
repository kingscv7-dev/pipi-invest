@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if exist "vr7.pid" (
    set /p VRPID=<"vr7.pid"
    if defined VRPID (
        tasklist /FI "PID eq !VRPID!" 2>nul | find "!VRPID!" >nul
        if not errorlevel 1 (
            start "" "http://127.0.0.1:5002/dashboard"
            exit /b 0
        )
    )
    del /q "vr7.pid" >nul 2>&1
)

echo ==== PIPI VR7 start %date% %time% ==== > "vr7_run.log"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 app.py >> "vr7_run.log" 2>&1
    set "RC=!ERRORLEVEL!"
    if "!RC!"=="0" exit /b 0
    echo py -3 failed with code !RC!. Trying python... >> "vr7_run.log"
)

where python >nul 2>&1
if not errorlevel 1 (
    python app.py >> "vr7_run.log" 2>&1
    set "RC=!ERRORLEVEL!"
    echo python failed with code !RC!. >> "vr7_run.log"
    exit /b !RC!
)

echo Python launcher not found. >> "vr7_run.log"
exit /b 9009
