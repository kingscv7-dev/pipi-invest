@echo off
cd /d "%~dp0"
wscript.exe "%~dp0RUN_HIDDEN.vbs"
exit /b 0
