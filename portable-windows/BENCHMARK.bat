@echo off
setlocal DisableDelayedExpansion
"%~dp0python\python.exe" -X utf8 -B "%~dp0portable.py" benchmark %*
set "result=%errorlevel%"
if not defined OFSI_NONINTERACTIVE pause
exit /b %result%
