@echo off
rem Starts the Spread Screener and opens it in the browser. Close this window to stop it.
cd /d "%~dp0"
python server.py
pause
