# voice-input

本地离线语音输入：按住 `Ctrl+Shift+Space` 说话，松开后识别文本自动粘贴到光标处。
全程本地推理（SenseVoice-Small ONNX，CPU），无任何联网。

## 打包机指南（能上网的电脑）

1. 安装 [miniconda](https://docs.conda.io/en/latest/miniconda.html) 并加入 PATH。
2. 拷贝整个项目目录到打包机（或 git clone）。
3. PowerShell 运行：

   ```powershell
   cd <项目根>\build
   .\build-offline.ps1
   ```

4. 成功后产出 `build\dist\voice-input-offline-<日期>.zip`（约 1.5GB）。
5. U 盘拷贝该 zip 到公司电脑。

打包脚本会：创建 py3.10 环境 → 装依赖 → 下载模型 → 跑单元测试 →
导出 runtime.zip → 组装离线包。任何一步失败会立即停止并报错。

## 公司机指南（离线部署）

1. 将 `voice-input-offline-<日期>.zip` 解压到任意目录（如 `C:\voice-input`）。
   **目录路径不要包含中文与空格**（conda 运行时兼容性考虑）。
2. 双击 `install.bat`：解压运行时 → 修路径 → 建桌面快捷方式 →（可选）开机自启 → 跑单元测试。
3. 自检（对着麦克风说 2 秒话）：

   ```bat
   runtime\python.exe -m app.selftest
   ```

   打印出识别文本即链路通畅。

4. 双击桌面 `voice-input` 快捷方式启动。控制台窗口显示日志，可最小化，勿关闭。
5. 按住 `Ctrl+Shift+Space` 说话，松开后文本自动粘贴到光标处。
6. 术语纠正：编辑 `terms.yaml`（立即生效需重启）。
7. 换热键 / 关提示音 / 关自动粘贴：编辑 `config.yaml` 后重启。

## 手工验收清单

- [ ] OpenCode Desktop 输入框按住说话 → 松开 → 文字出现
- [ ] 粘贴后 1.5 秒原剪贴板内容恢复
- [ ] IDEA 中 Ctrl+Shift+Space 被拦截（SmartType 失效属预期）
- [ ] 微信/浏览器中同样生效
- [ ] terms.yaml 修改后重启生效
- [ ] 长按热键 3 秒以上说话，无空格泄露进输入框

## 已知限制

- 前台为管理员权限窗口时，热键拦截与模拟粘贴可能失效（UIPI），
  请以非管理员身份运行 OpenCode Desktop。
- 剪贴板恢复仅支持文本，图片/文件类型的剪贴板内容会被覆盖。
- 与 IDEA SmartType 补全（Ctrl+Shift+Space）冲突，可在 config.yaml 换热键。
