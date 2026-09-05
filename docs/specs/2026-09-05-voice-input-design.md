# voice-input 设计文档

日期：2026-09-05
状态：已获用户批准

## 背景与目标

用户在公司内网环境下使用 OpenCode Desktop + GLM-5.3 编码，缺少语音输入手段。目标是搭建一个完全本地化的语音输入工具：按住热键说话，松开后识别结果自动粘贴到光标所在输入框（主要目标是 OpenCode Desktop 输入框，同时全局通用）。

**成功标准：**

- 全程离线运行，不依赖任何公网服务
- 按住 Ctrl+Shift+Space 说话，松开后 1 秒内完成识别并粘贴
- 中文为主、中英混合可识别，Java 生态术语（Java/Spring/MyBatis 等）通过术语表纠正
- 公司电脑安装无需管理员权限
- 全局生效：OpenCode Desktop、IDEA、微信、浏览器等任意应用

## 约束

- **纯内网**：公司电脑无法访问公网（git 通道除外）。所有依赖与模型必须离线拷贝。
- **打包机制作**：依赖包与模型在另一台能上网的 Windows 电脑上制作，U 盘拷贝。
- **目标机环境**：Windows 11，Python 3.13（不兼容 FunASR，故自带 Python 3.10 运行时），RTX 4060（不用 GPU，纯 CPU 推理已够快），Realtek 麦克风阵列，无管理员权限假设。

## 已确认的决策

| 决策点 | 结论 | 备注 |
|---|---|---|
| 技术方案 | FunASR ONNX（SenseVoice-Small）+ onnxruntime CPU | 离线包约 1.5GB，免 CUDA 依赖 |
| 交互方式 | 按住说话（push-to-talk） | 用户选择，放弃切换式/VAD |
| 默认热键 | Ctrl+Shift+Space | 与 IDEA SmartType 补全冲突，用户已知晓并接受，可在 config.yaml 修改 |
| 输出行为 | 自动写剪贴板 + 模拟 Ctrl+V 粘贴 + 1.5s 后恢复原剪贴板 | 恢复行为可关闭 |
| 术语处理 | 可编辑术语表后处理替换（terms.yaml） | SenseVoice 不支持热词偏置 |
| Python 运行时 | conda-pack 打包 Python 3.10 独立运行时 | 与公司机已有 3.13 隔离 |

## 架构与目录

```
C:\code\voice-input\
├── app\
│   ├── __init__.py
│   ├── main.py        # 入口：加载配置 → 加载模型 → 注册热键 → 事件循环
│   ├── hotkey.py      # 全局热键监听与拦截（keyboard 库）
│   ├── recorder.py    # 录音采集（sounddevice, 16kHz 单声道，内存 buffer）
│   ├── asr.py         # SenseVoice-Small ONNX 推理（funasr-onnx）
│   ├── terms.py       # 术语表后处理替换
│   ├── clipboard.py   # 剪贴板写入、延时恢复
│   ├── config.py      # config.yaml 加载与校验
│   └── selftest.py    # 自检：录 2 秒 → 识别 → 打印（不粘贴）
├── tests\
│   ├── test_terms.py
│   └── test_config.py
├── config.yaml
├── terms.yaml
├── build\
│   ├── build-offline.ps1   # 打包机一键脚本
│   └── packages.txt        # pip 依赖清单
├── models\sensevoice\        # SenseVoiceSmallOnnx 模型文件（~240MB）
├── runtime\                  # conda-pack 运行时（install.bat 解开生成）
├── install.bat               # 公司机一键安装
├── start-voice-input.bat     # 启动脚本
└── README.md                 # 打包机指南 + 公司机指南 + 验收清单
```

## 核心交互流程

```
按住 Ctrl+Shift+Space
  → 低音提示音"嘟"，开始录音（热键事件被拦截，不透传给前台应用）
说话…
松开
  → 录音停止
  → SenseVoice 识别（亚秒级）
  → 术语表纠正（terms.yaml 顺序替换）
  → 保存原剪贴板文本 → 写入识别文本
  → 模拟 Ctrl+V 粘贴到光标处
  → 1.5 秒后恢复原剪贴板文本
  → 高音提示音"嘟"完成
```

边界规则：

- 按住时长 < 300ms：视为误触，丢弃，不识别不粘贴
- 识别结果为空：不粘贴，三短音提示
- 识别进行中：忽略新的热键触发（防重入）
- 恢复剪贴板仅覆盖文本内容；原剪贴板若为文件/图片等非文本格式会丢失（已接受的权衡，可用配置关闭恢复）

## 组件职责

| 组件 | 职责 | 依赖 |
|---|---|---|
| hotkey.py | 监听全局组合键按下/松开，suppress 拦截；防重入锁 | keyboard |
| recorder.py | 按住时持续采集 16kHz mono int16 到内存，松开返回 numpy 数组 | sounddevice |
| asr.py | 加载 SenseVoice ONNX 模型，调用推理，返回文本（含标点、ITN） | funasr-onnx, onnxruntime |
| terms.py | 加载 terms.yaml，按序执行字符串/正则替换 | pyyaml |
| clipboard.py | 读原剪贴板文本、写入新文本、延时恢复；模拟 Ctrl+V | pyperclip, keyboard |
| config.py | 加载 config.yaml，缺失项回退默认值，校验热键格式 | pyyaml |
| selftest.py | 端到端验证：录音→识别→打印结果 | 上述全部 |

## 打包机流程（build-offline.ps1）

前置：一台能上网的 Windows 电脑，已装 miniconda。

1. `conda create -n vi-build python=3.10 -y`
2. `pip install -r packages.txt`（清华镜像加速）
3. `pip install conda-pack`
4. 通过 modelscope 包下载 `iic/SenseVoiceSmallOnnx` 到 `models\sensevoice\`
5. `conda-pack -n vi-build -o runtime.zip`
6. 汇总 `app\ + config.yaml + terms.yaml + build\ + models\ + runtime.zip + install.bat + start-voice-input.bat + README.md` 为 `voice-input-offline-<日期>.zip`（约 1.5GB）

packages.txt：funasr-onnx、onnxruntime、keyboard、sounddevice、numpy、pyperclip、pyyaml、modelscope（仅打包机下载模型用，会被 conda-pack 一并带入公司机，冗余无害）、pytest（公司机跑单测用）。

## 公司机安装流程（install.bat）

1. 用户将离线 zip 解压到任意目录（install.bat 在解压后的目录内运行，不假定固定路径；开发仓库本身位于 `C:\code\voice-input`，开发机上直接运行 install.bat 即可）
2. install.bat：
   - 展开 `runtime.zip` → `runtime\`
   - 运行 `runtime\Scripts\conda-unpack.exe` 修复路径前缀
   - 建桌面快捷方式（指向 start-voice-input.bat）
   - 询问是否加入开机自启（shell:startup 建快捷方式，可跳过）
   - 调用 `python -m app.selftest` 自检并打印结果
3. 不写注册表、不需要管理员权限

## 配置项设计（config.yaml）

| 键 | 默认值 | 说明 |
|---|---|---|
| hotkey | ctrl+shift+space | keyboard 库格式 |
| auto_paste | true | false 时仅写剪贴板不模拟粘贴 |
| restore_clipboard | true | 粘贴后 1.5s 恢复原剪贴板文本 |
| restore_delay_sec | 1.5 | 恢复延时 |
| beep | true | 录音开始/结束/错误提示音 |
| min_duration_ms | 300 | 短于该时长的录音视为误触丢弃 |
| sample_rate | 16000 | 采样率 |

## 术语表设计（terms.yaml）

```yaml
# 顺序替换，先匹配先得
rules:
  - pattern: "斯布林"
    replacement: "Spring"
  - pattern: "买八提寺"
    replacement: "MyBatis"
  - pattern: "(?i)spring boot"
    replacement: "Spring Boot"
    regex: true   # 可选，默认 false 为字面量替换
```

## 错误处理

| 场景 | 行为 |
|---|---|
| 麦克风不可用/被占用 | 启动时打开输入流失败 → 明确报错退出 |
| 模型文件缺失 | 启动时校验 models 目录关键文件，缺失即退出并提示 |
| config.yaml 损坏 | 报错退出，提示修复或删除后用默认值 |
| 识别结果为空 | 不粘贴，三短音提示 |
| 按住 <300ms | 静默丢弃 |
| 粘贴失败/前台为管理员窗口 | keyboard 模拟按键可能被 UIPI 拦截，README 注明以非管理员身份运行 OpenCode Desktop |

## 测试策略

- **pytest 单测**（打包机与公司机均可跑）：terms.py 替换逻辑（字面量/正则/顺序/空表）、config.py 默认值回退与校验
- **selftest 集成**：`python -m app.selftest` 录 2 秒→识别→打印，验证录音+模型链路，不碰剪贴板
- **手工验收清单**（README）：
  1. OpenCode Desktop 输入框按住说话→松开→文字出现
  2. 粘贴后原剪贴板内容被恢复
  3. IDEA 中 Ctrl+Shift+Space 被拦截（SmartType 失效属预期）
  4. 微信/浏览器中同样生效
  5. terms.yaml 修改后重启生效

## 风险与已接受的权衡

1. **IDEA SmartType 冲突**：Ctrl+Shift+Space 被 suppress 后 IDEA 无法使用该快捷键。用户已知晓，热键可改。
2. **剪贴板非文本内容丢失**：恢复机制仅支持文本。已接受。
3. **keyboard 库 suppress 的局限**：前台为管理员权限窗口时拦截与模拟按键可能失效。README 注明。
4. **conda-pack 跨机兼容**：同为 Windows x64 无问题，conda-unpack 修路径。
5. **SoundDevice 找不到设备**：依赖目标机驱动正常（已验证本机 OK）。

## 明确不做（YAGNI）

- 托盘图标 / GUI
- GPU 推理
- VAD 自动断句（按住说话模式不需要）
- 流式识别（亚秒级整句识别已够用）
- 多热键方案
- 剪贴板非文本格式保存/恢复
