@echo off
cd /d "%~dp0"
wscript.exe "%~dp0STOP_HIDDEN.vbs"
exit /b 0
