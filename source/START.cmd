@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python\python.exe" goto missing
"runtime\python\python.exe" -I -X utf8 launch.py
if errorlevel 1 pause
exit /b
:missing
echo Extract the COMPLETE full installation ZIP, including the runtime folder.
pause
exit /b 1
