@echo off
cd /d "%~dp0"
echo ========================================
echo PIPI VR7 DIAGNOSTIC
echo ========================================
echo.
echo [1] Python launcher
where py
py -3 --version
echo.
echo [2] Flask
py -3 -c "import flask; print('Flask', flask.__version__)"
echo.
echo [3] Starting app.py
py -3 app.py
set RC=%ERRORLEVEL%
echo.
echo app.py exit code: %RC%
echo Take a screenshot of this window if an error appears.
pause
