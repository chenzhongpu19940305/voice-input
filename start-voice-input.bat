@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" (
    echo [错误] 未找到 runtime\python.exe，请先运行 install.bat
    pause
    exit /b 1
)
"runtime\python.exe" -m app.main
pause
