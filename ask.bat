@echo off
REM ask.bat - launch local knowledge-base search (no API key needed)
REM Double-click to open interactive mode, or: ask.bat "your question"
chcp 65001 >nul
cd /d "%~dp0"
python ask.py %*
echo.
pause
