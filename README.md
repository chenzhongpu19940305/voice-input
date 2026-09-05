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

## 公司机指南

见下文（install.bat 部分由后续任务补充完整）。

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
