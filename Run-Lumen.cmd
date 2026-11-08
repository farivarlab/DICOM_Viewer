@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m lumen %*
    exit /b 0
)
echo Set up the development environment first. See README.md.
pause
exit /b 1
