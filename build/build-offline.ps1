# voice-input 离线包构建脚本 —— 在能上网的 Windows 电脑上运行。
# 前置：已安装 miniconda 并在 PATH 中；本脚本同目录的上级为项目根（含 app\ 等）。
# 产出: <项目根>\build\dist\voice-input-offline-<日期>.zip
# 说明: ModelScope 无现成 ONNX 版 SenseVoice，需用 funasr(torch) 从 PyTorch 版导出；
#       导出环境 vi-export 只用于导出，不打入 runtime.zip。
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envName = "vi-build"        # 轻量运行时（最终打入 runtime.zip）
$envExport = "vi-export"     # 导出工具环境（torch CPU + funasr）
# pip 源：默认官方 PyPI。国内镜像（清华/交大）对 funasr-onnx 包文件 403，不可用。
# 如需覆盖：$env:VI_PIP_INDEX = "https://pypi.org/simple"
$pipMirror = if ($env:VI_PIP_INDEX) { $env:VI_PIP_INDEX } else { "https://pypi.org/simple" }

function Ensure-CondaEnv($name) {
    if (-not (conda env list | Select-String -SimpleMatch $name)) {
        conda create -n $name python=3.10 -y
        if ($LASTEXITCODE -ne 0) { throw "conda create $name 失败" }
    } else {
        Write-Host "      环境 $name 已存在，跳过创建"
    }
}

Write-Host "[1/7] 准备运行时环境 $envName (python=3.10)…"
Ensure-CondaEnv $envName
$pyExe = Join-Path (conda info --base) "envs\$envName\python.exe"

Write-Host "[2/7] 安装运行时依赖（$pipMirror）…"
& $pyExe -m pip install -i $pipMirror -r (Join-Path $PSScriptRoot "packages.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }

Write-Host "[3/7] 准备导出环境 $envExport（torch CPU + funasr，约 2GB，仅导出用）…"
Ensure-CondaEnv $envExport
$pyExport = Join-Path (conda info --base) "envs\$envExport\python.exe"
& $pyExport -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "torch 安装失败" }
& $pyExport -m pip install -i $pipMirror funasr onnxscript onnxruntime
if ($LASTEXITCODE -ne 0) { throw "funasr 安装失败" }

Write-Host "[4/7] 下载并导出 SenseVoice ONNX 模型（下载 936MB + 导出，耗时较长）…"
# 注意1：PS5.1 给 python -c 传多行代码会被参数转义破坏 → 写临时 .py 文件
# 注意2：2>&1 会把 python 的 stderr 日志包装成 ErrorRecord（EAP=Stop 下直接终止脚本）
#        → 用 Start-Process 把 stdout/stderr 重定向到文件，事后按退出码判断
$exportPy = Join-Path $env:TEMP "vi_export_onnx.py"
@'
from funasr import AutoModel
model = AutoModel(model="iic/SenseVoiceSmall", device="cpu")
out = model.export(type="onnx", quantize=True)
print("EXPORT_DIR:" + str(out))
'@ | Out-File -FilePath $exportPy -Encoding utf8
$outLog = Join-Path $env:TEMP "vi-export-out.txt"
$errLog = Join-Path $env:TEMP "vi-export-err.txt"
Write-Host "      进度日志: $errLog （另开 PowerShell 窗口可实时查看：Get-Content 该文件 -Wait -Tail 20）"
$proc = Start-Process -FilePath $pyExport -ArgumentList ('"{0}"' -f $exportPy) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
if ($proc.ExitCode -ne 0) {
    Write-Host "------ 导出失败，stderr 最后 40 行 ------"
    Get-Content $errLog -Tail 40 | Write-Host
    throw "onnx 导出失败（退出码 $($proc.ExitCode)）"
}
$match = (Select-String -Path $outLog -Pattern "EXPORT_DIR:(.+)" | Select-Object -First 1)
if (-not $match) { throw "onnx 导出未返回目录，请查看 $outLog" }
$exportDir = $match.Matches.Groups[1].Value.Trim()
$modelDir = Join-Path $projectRoot "models\sensevoice"
New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
foreach ($f in @("model_quant.onnx", "chn_jpn_yue_eng_ko_spectok.bpe.model", "config.yaml", "am.mvn")) {
    Copy-Item (Join-Path $exportDir $f) -Destination $modelDir -Force
}
Write-Host "      模型已导出到 $modelDir"

Write-Host "[5/7] 单元测试（打包机上先保证逻辑全绿）…"
Push-Location $projectRoot
& $pyExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "单元测试未通过" }
Pop-Location

Write-Host "[6/7] conda-pack 导出 runtime.zip…"
# conda-pack 无 __main__，不能用 python -m，须用其 exe（装在 vi-build 的 Scripts 下）
$packExe = Join-Path (conda info --base) "envs\$envName\Scripts\conda-pack.exe"
if (-not (Test-Path $packExe)) { throw "未找到 $packExe" }
& $packExe -n $envName -o (Join-Path $env:TEMP "vi-runtime.zip") --force
if ($LASTEXITCODE -ne 0) { throw "conda-pack 失败" }

Write-Host "[7/7] 组装离线包…"
$dist = Join-Path $PSScriptRoot "dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null
# stage 必须在项目树之外：$items 含 build\，若 stage 在 build\ 内会把
# runtime.zip（vi-runtime.zip）再拷一份进 stage\build\，导致离线包体积翻倍。
$stage = Join-Path $env:TEMP "voice-input"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

$items = @("app", "tests", "build", "config.yaml", "terms.yaml",
           "start-voice-input.bat", ".gitignore", "install.bat", "README.md")
foreach ($item in $items) {
    if (Test-Path (Join-Path $projectRoot $item)) {
        Copy-Item (Join-Path $projectRoot $item) -Destination $stage -Recurse
    } else {
        throw "缺少打包必需文件: $item"
    }
}
Copy-Item (Join-Path $projectRoot "models") -Destination $stage -Recurse
Copy-Item (Join-Path $env:TEMP "vi-runtime.zip") -Destination (Join-Path $stage "runtime.zip")

$zip = Join-Path $dist ("voice-input-offline-{0}.zip" -f (Get-Date -Format "yyyyMMdd"))
Compress-Archive -Path $stage -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force
Remove-Item (Join-Path $env:TEMP "vi-runtime.zip") -Force

Write-Host "完成: $zip"
Write-Host "请将此 zip 拷贝到公司电脑并解压，运行 install.bat。"
Write-Host "（可选清理导出环境：conda env remove -n vi-export）"
