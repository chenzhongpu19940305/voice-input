# voice-input 离线包构建脚本 —— 在能上网的 Windows 电脑上运行。
# 前置：已安装 miniconda 并在 PATH 中；本脚本同目录的上级为项目根（含 app\ 等）。
# 产出: <项目根>\build\dist\voice-input-offline-<日期>.zip
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envName = "vi-build"
$pipMirror = "https://pypi.tuna.tsinghua.edu.cn/simple"

Write-Host "[1/6] 创建 conda 环境 $envName (python=3.10)…"
conda create -n $envName python=3.10 -y
if ($LASTEXITCODE -ne 0) { throw "conda create 失败" }

Write-Host "[2/6] 安装依赖（清华镜像）…"
$pyExe = Join-Path (conda info --base) "envs\$envName\python.exe"
& $pyExe -m pip install -i $pipMirror -r (Join-Path $PSScriptRoot "packages.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }

Write-Host "[3/6] 下载 SenseVoiceSmallOnnx 模型…"
$modelDir = Join-Path $projectRoot "models\sensevoice"
& $pyExe -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmallOnnx', local_dir=r'$modelDir')"
if ($LASTEXITCODE -ne 0) { throw "模型下载失败" }

Write-Host "[4/6] 单元测试（打包机上先保证逻辑全绿）…"
Push-Location $projectRoot
& $pyExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "单元测试未通过" }
Pop-Location

Write-Host "[5/6] conda-pack 导出 runtime.zip…"
& $pyExe -m conda_pack -n $envName -o (Join-Path $env:TEMP "vi-runtime.zip") --force
if ($LASTEXITCODE -ne 0) { throw "conda-pack 失败" }

Write-Host "[6/6] 组装离线包…"
$dist = Join-Path $PSScriptRoot "dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null
# stage 放在项目树之外的 TEMP：runtime.zip 已在 TEMP 产出（不随 build\ 拷入），
# stage 置于 TEMP 可避免"目录拷进自身子树"的嵌套拷贝问题与项目树残留。
$stage = Join-Path $env:TEMP "voice-input"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

$items = @("app", "tests", "build", "config.yaml", "terms.yaml",
           "start-voice-input.bat", ".gitignore")
foreach ($item in $items) {
    Copy-Item (Join-Path $projectRoot $item) -Destination $stage -Recurse
}
Copy-Item (Join-Path $projectRoot "install.bat") -Destination $stage -ErrorAction SilentlyContinue
Copy-Item (Join-Path $projectRoot "README.md") -Destination $stage -ErrorAction SilentlyContinue
Copy-Item (Join-Path $projectRoot "models") -Destination $stage -Recurse
Copy-Item (Join-Path $env:TEMP "vi-runtime.zip") -Destination (Join-Path $stage "runtime.zip")

$zip = Join-Path $dist ("voice-input-offline-{0}.zip" -f (Get-Date -Format "yyyyMMdd"))
Compress-Archive -Path $stage -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force
Remove-Item (Join-Path $env:TEMP "vi-runtime.zip") -Force

Write-Host "完成: $zip"
Write-Host "请将此 zip 拷贝到公司电脑并解压，运行 install.bat。"
