@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cls
echo ========================================
echo PIPI VR7 TABLET SETUP
echo ========================================
echo.
netsh advfirewall firewall delete rule name="PIPI VR7 5002" >nul 2>&1
netsh advfirewall firewall add rule name="PIPI VR7 5002" dir=in action=allow protocol=TCP localport=5002 remoteip=LocalSubnet profile=any >nul 2>&1

if "%errorlevel%"=="0" (
    echo FIREWALL: OK
    echo TCP 5002 allowed from LocalSubnet.
) else (
    echo FIREWALL: FAILED
)

echo.
echo Run RUN.bat, then TABLET_ADDRESS.bat.
echo ========================================
echo.
echo Press any key to close...
pause >nul
