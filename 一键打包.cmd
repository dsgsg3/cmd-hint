@echo off
cd /d "%~dp0cmdhint"
python build.py %*
echo.
pause
