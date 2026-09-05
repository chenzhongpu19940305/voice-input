@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo [1/4] 解压 runtime.zip（约需 2-5 分钟）…
if not exist runtime.zip (
    echo [错误] 当前目录没有 runtime.zip，请确认使用的是完整离线包
    pause
    exit /b 1
)
if exist runtime\ (
    echo        runtime\ 已存在，跳过解压。如需重装请先删除 runtime\ 目录
) else (
    tar -xf runtime.zip
    if errorlevel 1 (
        echo [错误] 解压失败
        pause
        exit /b 1
    )
)

echo [2/4] 修复运行时路径（conda-unpack）…
if not exist runtime\python.exe (
    echo [错误] 解压后未找到 runtime\python.exe
    pause
    exit /b 1
)
runtime\Scripts\conda-unpack.exe
if errorlevel 1 (
    echo [警告] conda-unpack 返回非零，Windows 上通常仍可运行，继续…
)

echo [3/4] 创建桌面快捷方式…
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut([IO.Path]::Combine($ws.SpecialFolders['Desktop'], 'voice-input.lnk')); $lnk.TargetPath = '%~dp0start-voice-input.bat'; $lnk.WorkingDirectory = '%~dp0'; $lnk.Save()"

set /p AUTOSTART=是否加入开机自启？(y/N)：
if /i "%AUTOSTART%"=="y" (
    powershell -NoProfile -Command ^
      "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut([IO.Path]::Combine($ws.SpecialFolders['Startup'], 'voice-input.lnk')); $lnk.TargetPath = '%~dp0start-voice-input.bat'; $lnk.WorkingDirectory = '%~dp0'; $lnk.Save()"
    echo        已加入开机自启
)

echo [4/4] 运行单元测试自检…
runtime\python.exe -m unittest discover -s tests -v

echo.
echo 安装完成。请先运行自检验证麦克风与模型：
echo     runtime\python.exe -m app.selftest
echo 之后双击桌面 voice-input 快捷方式即可使用。
pause
