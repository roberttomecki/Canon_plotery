@echo off
setlocal
py -3 "%~dp0Canon_plotery.py" %*
set "result=%errorlevel%"
pause
exit /b %result%
