# voice-input 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯本地离线语音输入工具——按住 Ctrl+Shift+Space 说话，松开后 SenseVoice 识别并自动粘贴到光标处。

**Architecture:** 常驻 Python 进程 = 全局热键(hook) → 录音(内存 buffer) → ONNX ASR → 术语替换 → 剪贴板+模拟粘贴+恢复。纯逻辑与硬件依赖严格分层，硬件库全部延迟导入。

**Tech Stack:** Python 3.10（离线 conda-pack 运行时）、funasr-onnx（SenseVoiceSmallOnnx）、onnxruntime CPU、keyboard、sounddevice、ctypes Win32（剪贴板）、PyYAML、unittest。

**Spec:** `docs/specs/2026-09-05-voice-input-design.md`

## Global Constraints

- **开发机为纯内网 Windows，仅有 stdlib + pyyaml**。测试运行器一律 `python -m unittest discover -s tests -v`，禁止依赖 pytest 运行（离线包仍带 pytest 供公司机使用）。
- 所有文件读写显式 `encoding="utf-8"`；bat 文件开头 `chcp 65001 >nul`。
- `keyboard`、`sounddevice`、`funasr_onnx`、`onnxruntime`、`numpy` **只允许在函数/方法体内 import**（延迟导入），模块顶层导入它们会导致内网开发机测试失败。
- 代码须同时兼容 Python 3.10（公司机 runtime）与 3.13（开发机）。仅用 3.10+ 语法。
- 术语表/配置文件格式见 spec「配置项设计」「术语表设计」两节，键名必须与 spec 完全一致。
- 剪贴板实现用 ctypes Win32 API（CF_UNICODETEXT），**不使用 pyperclip**（对 spec 的已批准偏差：减少依赖且内网开发机可真实测试）。
- 每个 Task 结束必须 commit。工作目录 `C:\code\voice-input`。

---

### Task 1: 项目骨架 + config.py

**Files:**
- Create: `app/__init__.py`（空文件）
- Create: `tests/__init__.py`（空文件）
- Create: `app/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `app.config.load_config(path: str) -> Config`；`Config` dataclass 字段：`hotkey: str`、`auto_paste: bool`、`restore_clipboard: bool`、`restore_delay_sec: float`、`beep: bool`、`min_duration_ms: int`、`sample_rate: int`；异常 `ConfigError(Exception)`。后续 Task 的 pipeline 用 `Config` 实例取这些字段。

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`：

```python
import os
import tempfile
import unittest

from app.config import Config, ConfigError, load_config


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(os.path.join(d, "nope.yaml"))
        self.assertEqual(cfg.hotkey, "ctrl+shift+space")
        self.assertTrue(cfg.auto_paste)
        self.assertTrue(cfg.restore_clipboard)
        self.assertEqual(cfg.restore_delay_sec, 1.5)
        self.assertTrue(cfg.beep)
        self.assertEqual(cfg.min_duration_ms, 300)
        self.assertEqual(cfg.sample_rate, 16000)

    def test_partial_file_keeps_defaults_for_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("hotkey: ctrl+shift+d\nbeep: false\n")
            cfg = load_config(p)
        self.assertEqual(cfg.hotkey, "ctrl+shift+d")
        self.assertFalse(cfg.beep)
        self.assertTrue(cfg.auto_paste)

    def test_full_file_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "hotkey: ctrl+alt+v\n"
                    "auto_paste: false\n"
                    "restore_clipboard: false\n"
                    "restore_delay_sec: 2.0\n"
                    "beep: false\n"
                    "min_duration_ms: 500\n"
                    "sample_rate: 16000\n"
                )
            cfg = load_config(p)
        self.assertEqual(cfg.hotkey, "ctrl+alt+v")
        self.assertFalse(cfg.auto_paste)
        self.assertFalse(cfg.restore_clipboard)
        self.assertEqual(cfg.restore_delay_sec, 2.0)
        self.assertEqual(cfg.min_duration_ms, 500)

    def test_bad_type_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("min_duration_ms: abc\n")
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_broken_yaml_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(":\n  - [broken\n")
            with self.assertRaises(ConfigError):
                load_config(p)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: 最小实现**

`app/config.py`：

```python
"""config.yaml 加载：缺失文件/缺失键回退默认值，类型错误抛 ConfigError。"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


class ConfigError(Exception):
    """配置文件无法解析或字段类型非法。"""


@dataclass
class Config:
    hotkey: str = "ctrl+shift+space"
    auto_paste: bool = True
    restore_clipboard: bool = True
    restore_delay_sec: float = 1.5
    beep: bool = True
    min_duration_ms: int = 300
    sample_rate: int = 16000


_FIELD_TYPES = {
    "hotkey": str,
    "auto_paste": bool,
    "restore_clipboard": bool,
    "restore_delay_sec": float,
    "beep": bool,
    "min_duration_ms": int,
    "sample_rate": int,
}


def load_config(path: str) -> Config:
    if not os.path.isfile(path):
        return Config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml 语法错误: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml 顶层必须是键值映射")
    values = {}
    for key, typ in _FIELD_TYPES.items():
        if key in raw and raw[key] is not None:
            value = raw[key]
            if typ is float and isinstance(value, int):
                value = float(value)
            if not isinstance(value, typ) or isinstance(value, bool) != (typ is bool):
                raise ConfigError(
                    f"配置项 {key} 期望 {typ.__name__}，实际为 {value!r}"
                )
            values[key] = value
    return Config(**values)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 5 tests OK

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: config 加载与默认值回退"
```

---

### Task 2: terms.py 术语替换

**Files:**
- Create: `app/terms.py`
- Test: `tests/test_terms.py`

**Interfaces:**
- Consumes: 无
- Produces: `app.terms.TermRule`（dataclass：`pattern: str`、`replacement: str`、`regex: bool = False`）；`load_terms(path: str) -> list[TermRule]`（文件缺失/无 rules 键 → `[]`；regex 编译失败抛 `TermsError`）；`apply_terms(text: str, rules: list[TermRule]) -> str`（按列表顺序替换）。

- [ ] **Step 1: 写失败测试**

`tests/test_terms.py`：

```python
import os
import tempfile
import unittest

from app.terms import TermRule, TermsError, apply_terms, load_terms


class TestLoadTerms(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_terms(os.path.join(d, "nope.yaml")), [])

    def test_no_rules_key_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("rules: []\n")
            self.assertEqual(load_terms(p), [])

    def test_load_rules(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "rules:\n"
                    "  - pattern: 斯布林\n"
                    "    replacement: Spring\n"
                    "  - pattern: (?i)spring boot\n"
                    "    replacement: Spring Boot\n"
                    "    regex: true\n"
                )
            rules = load_terms(p)
        self.assertEqual(rules[0], TermRule("斯布林", "Spring"))
        self.assertEqual(rules[1], TermRule("(?i)spring boot", "Spring Boot", regex=True))

    def test_bad_regex_raises_terms_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "rules:\n"
                    "  - pattern: '[unclosed'\n"
                    "    replacement: X\n"
                    "    regex: true\n"
                )
            with self.assertRaises(TermsError):
                load_terms(p)


class TestApplyTerms(unittest.TestCase):
    def test_no_rules_passthrough(self):
        self.assertEqual(apply_terms("帮我看看斯布林", []), "帮我看看斯布林")

    def test_literal_replace(self):
        rules = [TermRule("斯布林", "Spring")]
        self.assertEqual(apply_terms("用斯布林写接口", rules), "用Spring写接口")

    def test_order_matters(self):
        rules = [
            TermRule("斯布林布特", "Spring Boot"),
            TermRule("斯布林", "Spring"),
        ]
        self.assertEqual(apply_terms("斯布林布特和斯布林", rules), "Spring Boot和Spring")

    def test_regex_replace(self):
        rules = [TermRule("(?i)spring\\s+boot", "Spring Boot", regex=True)]
        self.assertEqual(apply_terms("升级spring BOOT 到3", rules), "升级Spring Boot 到3")

    def test_mixed_rules(self):
        rules = [
            TermRule("买八提寺", "MyBatis"),
            TermRule("([a-z]+)\\s*boot", r"\1 Boot", regex=True),
        ]
        self.assertEqual(apply_terms("用买八提寺和springboot搭", rules), "用MyBatis和spring Boot搭")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.terms'`

- [ ] **Step 3: 最小实现**

`app/terms.py`：

```python
"""术语表加载与识别结果后处理替换。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import yaml


class TermsError(Exception):
    """术语表无法解析或正则非法。"""


@dataclass(frozen=True)
class TermRule:
    pattern: str
    replacement: str
    regex: bool = False


def load_terms(path: str) -> list[TermRule]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise TermsError(f"terms.yaml 语法错误: {exc}") from exc
    entries = raw.get("rules") or []
    rules: list[TermRule] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or "pattern" not in entry or "replacement" not in entry:
            raise TermsError(f"terms.yaml 第 {i + 1} 条规则缺少 pattern/replacement")
        rule = TermRule(
            pattern=str(entry["pattern"]),
            replacement=str(entry["replacement"]),
            regex=bool(entry.get("regex", False)),
        )
        if rule.regex:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise TermsError(f"terms.yaml 第 {i + 1} 条正则非法: {exc}") from exc
        rules.append(rule)
    return rules


def apply_terms(text: str, rules: list[TermRule]) -> str:
    result = text
    for rule in rules:
        if rule.regex:
            result = re.sub(rule.pattern, rule.replacement, result)
        else:
            result = result.replace(rule.pattern, rule.replacement)
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 9 tests OK

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: 术语表加载与替换"
```

---

### Task 3: clipboard.py（ctypes Win32 剪贴板）

**Files:**
- Create: `app/clipboard.py`
- Test: `tests/test_clipboard.py`

**Interfaces:**
- Consumes: 无（纯 ctypes + stdlib）
- Produces: `app.clipboard.get_clipboard_text() -> str | None`（无文本时 None）；`app.clipboard.set_clipboard_text(text: str) -> None`；`app.clipboard.restore_clipboard_later(original: str | None, delay_sec: float) -> threading.Timer`（original 为 None 则只清空？否——None 时不动剪贴板，直接返回已取消的 Timer）；`app.clipboard.CLIPBOARD_UNAVAILABLE`（异常，OpenClipboard 失败时抛，公司机被独占场景）。

**注意：** 测试会真实操作剪贴板，`setUp` 保存原文本、`tearDown` 恢复。

- [ ] **Step 1: 写失败测试**

`tests/test_clipboard.py`：

```python
import unittest

from app import clipboard


class TestClipboardRoundTrip(unittest.TestCase):
    def setUp(self):
        self._original = clipboard.get_clipboard_text()
        # 清空剪贴板
        clipboard.set_clipboard_text("")

    def tearDown(self):
        if self._original is not None:
            clipboard.set_clipboard_text(self._original)

    def test_set_then_get(self):
        clipboard.set_clipboard_text("hello 语音")
        self.assertEqual(clipboard.get_clipboard_text(), "hello 语音")

    def test_get_after_empty_returns_none_or_empty(self):
        # set("") 后允许返回 None 或 ""，但不能是旧内容
        value = clipboard.get_clipboard_text()
        self.assertIn(value, (None, ""))

    def test_unicode_roundtrip(self):
        text = "中文 English Java✅ 换行\n第二行"
        clipboard.set_clipboard_text(text)
        self.assertEqual(clipboard.get_clipboard_text(), text)

    def test_restore_later_none_does_nothing(self):
        timer = clipboard.restore_clipboard_later(None, delay_sec=0.05)
        self.assertFalse(timer.is_alive())

    def test_restore_later_restores_text(self):
        clipboard.set_clipboard_text("识别结果")
        clipboard.set_clipboard_text("临时覆盖")
        timer = clipboard.restore_clipboard_later("识别结果", delay_sec=0.05)
        timer.join(timeout=2)
        self.assertEqual(clipboard.get_clipboard_text(), "识别结果")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.clipboard'`

- [ ] **Step 3: 最小实现**

`app/clipboard.py`：

```python
"""Win32 剪贴板读写（CF_UNICODETEXT），ctypes 实现，无第三方依赖。"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]


class CLIPBOARD_UNAVAILABLE(Exception):
    """无法打开剪贴板（被其他进程独占等）。"""


class _ClipboardSession:
    """OpenClipboard/CloseClipboard 上下文管理器。"""

    def __enter__(self):
        # 重试：剪贴板可能被其他进程短暂占用
        for _ in range(10):
            if user32.OpenClipboard(None):
                return self
            import time

            time.sleep(0.01)
        raise CLIPBOARD_UNAVAILABLE("OpenClipboard 失败（剪贴板被占用）")

    def __exit__(self, *exc):
        user32.CloseClipboard()
        return False


def get_clipboard_text() -> "str | None":
    with _ClipboardSession():
        handle = user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)


def set_clipboard_text(text: str) -> None:
    data = text.encode("utf-16-le") + b"\x00\x00"
    with _ClipboardSession():
        user32.EmptyClipboard()
        if text == "":
            return
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            raise MemoryError("GlobalAlloc 失败")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise MemoryError("GlobalLock 失败")
        try:
            ctypes.memmove(ptr, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
            raise CLIPBOARD_UNAVAILABLE("SetClipboardData 失败")


def restore_clipboard_later(original: "str | None", delay_sec: float) -> threading.Timer:
    """delay_sec 秒后把剪贴板恢复为 original；original 为 None 时不动剪贴板。"""
    if original is None:
        timer = threading.Timer(0, lambda: None)
        timer.cancel()
        return timer

    def _restore():
        try:
            set_clipboard_text(original)
        except Exception:
            pass  # 恢复失败不影响主流程

    timer = threading.Timer(delay_sec, _restore)
    timer.daemon = True
    timer.start()
    return timer
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 14 tests OK（前两任务 + 本任务 5 个）

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: ctypes Win32 剪贴板读写与延时恢复"
```

---

### Task 4: recorder.py（录音 buffer）

**Files:**
- Create: `app/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: 无（sounddevice 延迟导入）
- Produces: `app.recorder.audio_duration_seconds(pcm: bytes, sample_rate: int = 16000) -> float`（int16 单声道 PCM 时长）；`app.recorder.MicRecorder(sample_rate: int = 16000)`：`start() -> None`（开始采集）、`stop() -> bytes`（停止并返回全部 int16 LE PCM 数据）、内部回调 `_on_data(indata, frames, time_info, status)`（sounddevice InputStream 回调签名）；未 start 就 stop 抛 `RuntimeError`。`start()` 内部延迟 `import sounddevice` 并打开 `InputStream(samplerate, channels=1, dtype="int16", callback=self._on_data)`。

- [ ] **Step 1: 写失败测试**

`tests/test_recorder.py`：

```python
import unittest

from app.recorder import MicRecorder, audio_duration_seconds


class _FakeChunk:
    """模拟 sounddevice 的 indata：只暴露 tobytes()。"""

    def __init__(self, data: bytes):
        self._data = data

    def tobytes(self) -> bytes:
        return self._data


class TestDuration(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(audio_duration_seconds(b""), 0.0)

    def test_one_second(self):
        # int16 mono 16kHz: 1 秒 = 32000 字节
        self.assertAlmostEqual(audio_duration_seconds(b"\x00" * 32000), 1.0)

    def test_half_second(self):
        self.assertAlmostEqual(audio_duration_seconds(b"\x00" * 16000), 0.5)

    def test_other_sample_rate(self):
        self.assertAlmostEqual(audio_duration_seconds(b"\x00" * 16000, sample_rate=8000), 1.0)


class TestBuffer(unittest.TestCase):
    def test_stop_without_start_raises(self):
        rec = MicRecorder()
        with self.assertRaises(RuntimeError):
            rec.stop()

    def test_data_accumulates_across_callbacks(self):
        rec = MicRecorder()
        rec._recording = True
        rec._on_data(_FakeChunk(b"\x01\x02"), 1, None, None)
        rec._on_data(_FakeChunk(b"\x03\x04\x05\x06"), 2, None, None)
        self.assertEqual(rec._drain(), bytes([1, 2, 3, 4, 5, 6]))

    def test_drain_resets_buffer(self):
        rec = MicRecorder()
        rec._recording = True
        rec._on_data(_FakeChunk(b"\x01\x02"), 1, None, None)
        first = rec._drain()
        second = rec._drain()
        self.assertEqual(first, b"\x01\x02")
        self.assertEqual(second, b"")

    def test_callback_while_not_recording_drops_data(self):
        rec = MicRecorder()
        rec._recording = False
        rec._on_data(_FakeChunk(b"\x01\x02"), 1, None, None)
        self.assertEqual(rec._drain(), b"")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.recorder'`

- [ ] **Step 3: 最小实现**

`app/recorder.py`：

```python
"""按住式麦克风录音：int16 mono PCM 采集到内存 buffer。"""
from __future__ import annotations

import threading


def audio_duration_seconds(pcm: bytes, sample_rate: int = 16000) -> float:
    """int16 单声道 PCM 字节数换算时长（秒）。"""
    return len(pcm) / 2 / sample_rate


class MicRecorder:
    """start() 打开输入流，stop() 关闭并返回全部 PCM bytes。"""

    def __init__(self, sample_rate: int = 16000):
        self._sample_rate = sample_rate
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._recording = False
        self._stream = None

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        import sounddevice as sd  # 延迟导入：内网开发机无此库

        with self._lock:
            self._buffer = bytearray()
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            callback=self._on_data,
        )
        self._stream.start()
        self._recording = True

    def stop(self) -> bytes:
        if not self._recording:
            raise RuntimeError("stop() 在未 start() 时调用")
        stream, self._stream = self._stream, None
        self._recording = False
        if stream is not None:
            stream.stop()
            stream.close()
        return self._drain()

    def _on_data(self, indata, frames, time_info, status) -> None:
        if not self._recording:
            return
        with self._lock:
            self._buffer.extend(indata.tobytes())

    def _drain(self) -> bytes:
        with self._lock:
            data = bytes(self._buffer)
            self._buffer = bytearray()
        return data
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 20 tests OK

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: 麦克风录音 buffer 与时长计算"
```

---

### Task 5: asr.py（模型校验 + 推理封装）

**Files:**
- Create: `app/asr.py`
- Test: `tests/test_asr.py`

**Interfaces:**
- Consumes: 无
- Produces: `app.asr.REQUIRED_FILES`（tuple，模型目录必须存在的文件名）；`app.asr.validate_model_dir(model_dir: str) -> list[str]`（返回缺失文件名列表）；`app.asr.ASREngine`：类方法 `load(model_dir: str) -> ASREngine`（先 validate，缺失抛 `ModelError`；依赖缺失抛 `DependencyMissingError`）；`transcribe(pcm: bytes) -> str`（int16 PCM → float32 归一化 → SenseVoice 推理 → 文本，strip 后返回）。

**实现说明：** funasr_onnx 的 `SenseVoiceSmall(model_dir, quantize=True)` 加载目录下 `model.integer.onnx` 与分词器 `chn_jpn_yue_eng_ko_spectok.bpe.txt`；调用签名为 `model(audio_ndarray, fs=16000, language="auto", use_itn=True)`，返回结果取 `[0]`。**此 API 细节以离线包就位后的真机验证为准**（见 Task 11），若文件名/返回结构与预期不符，只需修正 `REQUIRED_FILES` 常量与 `transcribe` 解包行。

- [ ] **Step 1: 写失败测试**

`tests/test_asr.py`：

```python
import os
import tempfile
import unittest

from app.asr import (
    REQUIRED_FILES,
    ASREngine,
    DependencyMissingError,
    ModelError,
    validate_model_dir,
)


class TestValidateModelDir(unittest.TestCase):
    def test_empty_dir_reports_all_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing = validate_model_dir(d)
        self.assertEqual(sorted(missing), sorted(REQUIRED_FILES))

    def test_missing_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            os.remove(os.path.join(d, REQUIRED_FILES[0]))
            missing = validate_model_dir(d)
        self.assertEqual(missing, [REQUIRED_FILES[0]])

    def test_complete_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            self.assertEqual(validate_model_dir(d), [])

    def test_nonexistent_dir_reports_all(self):
        self.assertEqual(sorted(validate_model_dir(r"C:\no\such\dir")), sorted(REQUIRED_FILES))


class TestASREngineLoad(unittest.TestCase):
    def test_load_missing_model_raises_model_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ModelError):
                ASREngine.load(d)

    def test_load_without_dependency_raises_dependency_missing(self):
        # 内网开发机没有 funasr_onnx：先造完整假模型目录再 load，
        # 期望被 DependencyMissingError 拦截而不是 ImportError 裸抛。
        # 若公司机装好依赖后此测试失败（真的 import 成功），标记 skip：
        try:
            import funasr_onnx  # noqa: F401

            self.skipTest("本机装有 funasr_onnx，跳过缺依赖分支")
        except ImportError:
            pass
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            with self.assertRaises(DependencyMissingError):
                ASREngine.load(d)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.asr'`

- [ ] **Step 3: 最小实现**

`app/asr.py`：

```python
"""SenseVoice-Small ONNX 推理封装。依赖延迟导入，内网开发机可安全 import 本模块。"""
from __future__ import annotations

REQUIRED_FILES = (
    "model.integer.onnx",
    "chn_jpn_yue_eng_ko_spectok.bpe.txt",
)


class ModelError(Exception):
    """模型目录缺失或损坏。"""


class DependencyMissingError(Exception):
    """运行依赖未安装（离线包未解包/未 conda-unpack）。"""


def validate_model_dir(model_dir: str) -> list:
    """返回模型目录中缺失的必需文件名列表。"""
    import os

    return [name for name in REQUIRED_FILES if not os.path.isfile(os.path.join(model_dir, name))]


class ASREngine:
    def __init__(self, model, np):
        self._model = model
        self._np = np

    @classmethod
    def load(cls, model_dir: str) -> "ASREngine":
        missing = validate_model_dir(model_dir)
        if missing:
            raise ModelError(f"模型目录 {model_dir} 缺失文件: {missing}")
        try:
            import numpy as np
            from funasr_onnx import SenseVoiceSmall
        except ImportError as exc:
            raise DependencyMissingError(
                "推理依赖未安装（numpy/funasr_onnx），请确认离线包已解压并运行过 conda-unpack"
            ) from exc
        model = SenseVoiceSmall(model_dir, quantize=True)
        return cls(model, np)

    def transcribe(self, pcm: bytes) -> str:
        audio = self._np.frombuffer(pcm, dtype=self._np.int16).astype(self._np.float32) / 32768.0
        result = self._model(audio, fs=16000, language="auto", use_itn=True)
        if isinstance(result, list):
            result = result[0] if result else ""
        return str(result).strip()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 26 tests OK

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: 模型目录校验与 ASR 推理封装"
```

---

### Task 6: pipeline.py（按住说话编排状态机）

**Files:**
- Create: `app/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Config`（Task 1）、`TermRule`（Task 2）、`audio_duration_seconds`（Task 4）
- Produces: `app.pipeline.VoicePipeline`，构造参数（全部关键字）：`config: Config`、`recorder`（需 `start()/stop()->bytes`）、`engine`（需 `transcribe(bytes)->str`）、`rules: list[TermRule]`、`clipboard_get: Callable[[], str|None]`、`clipboard_set: Callable[[str], None]`、`paste: Callable[[], None]`、`restore: Callable[[str|None], None]`、`beep: Callable[[str], None]`（参数为 `"start"|"done"|"error"`）；方法 `on_press() -> None`、`on_release() -> None`；属性 `state`（`"idle"|"recording"|"recognizing"`）。

**行为规范（测试即规范）：**
1. on_press：idle → 低音 beep("start") → recorder.start() → state=recording
2. on_release：recording → stop 取 PCM → 时长 < config.min_duration_ms → 静默丢弃回 idle（不识别）
3. 正常流：transcribe → 空 strip → beep("error") 三短音、不写剪贴板不粘贴、回 idle
4. 有文本：apply_terms → clipboard_get 存原值 → clipboard_set(文本) → auto_paste 则 paste() → restore_clipboard 则 restore(原值) → beep("done") → idle
5. auto_paste=False：不调用 paste，其余照旧
6. restore_clipboard=False：不调用 restore
7. engine.transcribe 抛异常：beep("error")，回 idle，异常不外泄
8. 防重入：state 非 idle 时 on_press 无效果；recognizing 时 on_release 无效果
9. 未按下就 on_release：无效果不崩溃
10. beep=False（config）：任何情况不调用 beep 函数

- [ ] **Step 1: 写失败测试**

`tests/test_pipeline.py`：

```python
import unittest

from app.config import Config
from app.pipeline import VoicePipeline
from app.terms import TermRule


class FakeRecorder:
    def __init__(self, pcm=b"\x00" * 32000):  # 默认 1 秒
        self.pcm = pcm
        self.started = 0

    def start(self):
        self.started += 1

    def stop(self):
        return self.pcm


class FakeEngine:
    def __init__(self, text="识别文本"):
        self.text = text

    def transcribe(self, pcm):
        return self.text


class BoomEngine:
    def transcribe(self, pcm):
        raise RuntimeError("asr failed")


class Harness:
    def __init__(self, config=None, recorder=None, engine=None, rules=None):
        self.config = config or Config()
        self.recorder = recorder or FakeRecorder()
        self.engine = engine or FakeEngine()
        self.rules = rules or []
        self.events = {"beeps": [], "pastes": 0, "restores": [], "sets": [], "originals": []}
        self.pipe = VoicePipeline(
            config=self.config,
            recorder=self.recorder,
            engine=self.engine,
            rules=self.rules,
            clipboard_get=lambda: "旧剪贴板",
            clipboard_set=self.events["sets"].append,
            paste=self._paste,
            restore=self.events["restores"].append,
            beep=self.events["beeps"].append,
        )

    def _paste(self):
        self.events["pastes"] += 1


class TestNormalFlow(unittest.TestCase):
    def test_press_release_full_cycle(self):
        h = Harness()
        h.pipe.on_press()
        self.assertEqual(h.pipe.state, "recording")
        self.assertEqual(h.events["beeps"], ["start"])
        self.assertEqual(h.recorder.started, 1)
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], ["识别文本"])
        self.assertEqual(h.events["pastes"], 1)
        self.assertEqual(h.events["restores"], ["旧剪贴板"])
        self.assertEqual(h.events["beeps"], ["start", "done"])

    def test_terms_applied(self):
        h = Harness(rules=[TermRule("识别", "RECOG")])
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["sets"], ["RECOG文本"])

    def test_auto_paste_off(self):
        h = Harness(config=Config(auto_paste=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["sets"], ["识别文本"])
        self.assertEqual(h.events["pastes"], 0)
        self.assertEqual(h.events["restores"], ["旧剪贴板"])

    def test_restore_off(self):
        h = Harness(config=Config(restore_clipboard=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["pastes"], 1)
        self.assertEqual(h.events["restores"], [])


class TestEdgeCases(unittest.TestCase):
    def test_too_short_dropped_silently(self):
        h = Harness(recorder=FakeRecorder(pcm=b"\x00" * 1600))  # 50ms < 300ms
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], [])
        self.assertEqual(h.events["beeps"], ["start"])  # 只有开始音

    def test_empty_text_error_beep_no_paste(self):
        h = Harness(engine=FakeEngine(text="   "))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["beeps"], ["start", "error"])
        self.assertEqual(h.events["sets"], [])
        self.assertEqual(h.events["pastes"], 0)

    def test_engine_exception_contained(self):
        h = Harness(engine=BoomEngine())
        h.pipe.on_press()
        h.pipe.on_release()  # 不应抛出
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["beeps"], ["start", "error"])

    def test_press_while_recording_ignored(self):
        h = Harness()
        h.pipe.on_press()
        h.pipe.on_press()
        self.assertEqual(h.recorder.started, 1)

    def test_press_while_recognizing_ignored(self):
        h = Harness()
        states = []

        class SlowEngine:
            def transcribe(self, pcm):
                states.append(h.pipe.state)
                return "慢结果"

        h.engine = SlowEngine()
        h.pipe = VoicePipeline(
            config=h.config, recorder=h.recorder, engine=h.engine, rules=[],
            clipboard_get=lambda: None, clipboard_set=lambda t: None,
            paste=lambda: None, restore=lambda o: None, beep=lambda k: None,
        )
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(states, ["recognizing"])
        # 完整周期后可再次触发
        h.pipe.on_press()
        self.assertEqual(h.pipe.state, "recording")

    def test_release_without_press_noop(self):
        h = Harness()
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], [])

    def test_beep_off(self):
        h = Harness(config=Config(beep=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["beeps"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.pipeline'`

- [ ] **Step 3: 最小实现**

`app/pipeline.py`：

```python
"""按住说话编排状态机：热键事件 → 录音 → 识别 → 术语 → 剪贴板 → 粘贴。"""
from __future__ import annotations

import threading

from .config import Config
from .recorder import audio_duration_seconds
from .terms import TermRule, apply_terms


class VoicePipeline:
    def __init__(
        self,
        *,
        config: Config,
        recorder,
        engine,
        rules: list[TermRule],
        clipboard_get,
        clipboard_set,
        paste,
        restore,
        beep,
    ):
        self._config = config
        self._recorder = recorder
        self._engine = engine
        self._rules = rules
        self._clipboard_get = clipboard_get
        self._clipboard_set = clipboard_set
        self._paste = paste
        self._restore = restore
        self._beep = beep
        self._lock = threading.Lock()
        self._state = "idle"

    @property
    def state(self) -> str:
        return self._state

    def on_press(self) -> None:
        with self._lock:
            if self._state != "idle":
                return
            self._state = "recording"
        self._beep("start") if self._config.beep else None
        self._recorder.start()

    def on_release(self) -> None:
        with self._lock:
            if self._state != "recording":
                return
            self._state = "recognizing"
        try:
            pcm = self._recorder.stop()
            duration_ms = audio_duration_seconds(pcm, self._config.sample_rate) * 1000
            if duration_ms < self._config.min_duration_ms:
                with self._lock:
                    self._state = "idle"
                return
            text = apply_terms(self._engine.transcribe(pcm).strip(), self._rules)
            if not text:
                self._beep("error") if self._config.beep else None
                return
            original = self._clipboard_get()
            self._clipboard_set(text)
            if self._config.auto_paste:
                self._paste()
            if self._config.restore_clipboard:
                self._restore(original)
            self._beep("done") if self._config.beep else None
        except Exception:
            self._beep("error") if self._config.beep else None
        finally:
            with self._lock:
                self._state = "idle"
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m unittest discover -s tests -v`
Expected: 35 tests OK

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat: 按住说话编排状态机（含防重入与错误抑制）"
```

---

### Task 7: hotkey.py + main.py + selftest.py

**Files:**
- Create: `app/hotkey.py`
- Create: `app/main.py`
- Create: `app/selftest.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: `Config`（Task 1）、`VoicePipeline`（Task 6）、`MicRecorder`（Task 4）、`ASREngine`（Task 5）、`load_terms`（Task 2）、`clipboard`（Task 3）
- Produces: `app.hotkey.parse_hotkey(hotkey_str: str) -> list[str]`（`"ctrl+shift+space"` → `["ctrl","shift","space"]`，小写化、空白容忍、空段抛 `ValueError`）；`app.hotkey.HotkeyMatcher(mods: list[str], trigger: str, is_pressed: Callable[[str], bool])`：`matches(event_name: str) -> bool`（trigger 键名匹配且全部修饰键按下）；`app.hotkey.register_push_to_talk(hotkey_str: str, on_press, on_release) -> None`（延迟 import keyboard，keyboard.hook(suppress=True)，回调里：space down 且修饰键齐 → on_press + 返回 False 拦截；armed 后 space up → on_release + 返回 False；其余事件返回 True 放行——Windows only 语义，真机验证见 Task 11）；`app.main.main() -> int`；`python -m app.selftest`（录 2 秒 → 识别 → 打印，不粘贴）；`app/beep.py` 无——提示音内联在 main.py 的 `make_beep(enabled: bool)`（winsound.Beep：start=440Hz 80ms、done=880Hz 120ms、error=220Hz 三次 60ms）。

- [ ] **Step 1: 写失败测试**

`tests/test_hotkey.py`：

```python
import unittest

from app.hotkey import HotkeyMatcher, parse_hotkey


class TestParseHotkey(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_hotkey("ctrl+shift+space"), ["ctrl", "shift", "space"])

    def test_normalizes_case_and_spaces(self):
        self.assertEqual(parse_hotkey(" Ctrl + ALT + V "), ["ctrl", "alt", "v"])

    def test_single_key(self):
        self.assertEqual(parse_hotkey("f9"), ["f9"])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_hotkey("")
        with self.assertRaises(ValueError):
            parse_hotkey("ctrl++v")


class TestHotkeyMatcher(unittest.TestCase):
    def setUp(self):
        self.pressed = set()

        def is_pressed(name):
            return name in self.pressed

        self.matcher = HotkeyMatcher(mods=["ctrl", "shift"], trigger="space", is_pressed=is_pressed)

    def test_trigger_with_all_mods_matches(self):
        self.pressed.update(["ctrl", "shift"])
        self.assertTrue(self.matcher.matches("space"))

    def test_missing_mod_no_match(self):
        self.pressed.add("ctrl")
        self.assertFalse(self.matcher.matches("space"))

    def test_wrong_trigger(self):
        self.pressed.update(["ctrl", "shift"])
        self.assertFalse(self.matcher.matches("v"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m unittest discover -s tests -v`
Expected: ERROR — `No module named 'app.hotkey'`

- [ ] **Step 3: 实现 hotkey.py**

`app/hotkey.py`：

```python
"""全局热键：parse/match 纯逻辑可测；注册用 keyboard 库（延迟导入）。"""
from __future__ import annotations

from typing import Callable


def parse_hotkey(hotkey_str: str) -> list:
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    if not hotkey_str.strip() or any(not p for p in parts):
        raise ValueError(f"非法热键表达式: {hotkey_str!r}")
    return parts


class HotkeyMatcher:
    """trigger 键名匹配且全部修饰键处于按下状态时 matches 为 True。"""

    def __init__(self, mods: list, trigger: str, is_pressed: Callable[[str], bool]):
        self._mods = mods
        self._trigger = trigger
        self._is_pressed = is_pressed

    def matches(self, event_name: str) -> bool:
        if event_name != self._trigger:
            return False
        return all(self._is_pressed(m) for m in self._mods)


def register_push_to_talk(hotkey_str: str, on_press: Callable[[], None],
                          on_release: Callable[[], None]) -> None:
    """注册按住式全局热键并阻塞监听（keyboard 库，Windows）。

    suppress=True + 回调返回 False 拦截目标键事件（不透传给前台应用，
    避免空格进入 OpenCode Desktop 输入框）；返回 True 放行其他按键。
    拦截效果依赖 keyboard 库 Windows suppress 语义，真机验证见验证清单。
    """
    import keyboard  # 延迟导入：内网开发机无此库

    keys = parse_hotkey(hotkey_str)
    matcher = HotkeyMatcher(keys[:-1], keys[-1], keyboard.is_pressed)
    armed = False

    def on_event(event):
        nonlocal armed
        if event.name != keys[-1]:
            return True
        if event.event_type == "down" and not armed and matcher.matches(event.name):
            armed = True
            on_press()
            return False
        if event.event_type == "up" and armed:
            armed = False
            on_release()
            return False
        return True

    keyboard.hook(on_event, suppress=True)
    keyboard.wait()  # 阻塞直到进程退出
```

- [ ] **Step 4: 运行确认通过（hotkey 部分）**

Run: `python -m unittest discover -s tests -v`
Expected: 43 tests OK

- [ ] **Step 5: 实现 main.py 与 selftest.py（装配层，无单测——硬件全真）**

`app/main.py`：

```python
"""装配入口：配置 → 模型 → 管线 → 热键。"""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_beep(enabled: bool):
    import winsound

    def beep(kind: str) -> None:
        if not enabled:
            return
        if kind == "start":
            winsound.Beep(440, 80)
        elif kind == "done":
            winsound.Beep(880, 120)
        elif kind == "error":
            for _ in range(3):
                winsound.Beep(220, 60)

    return beep


def make_paste():
    import keyboard

    def paste() -> None:
        keyboard.send("ctrl+v")

    return paste


def main() -> int:
    from .asr import ASREngine, DependencyMissingError, ModelError
    from .clipboard import restore_clipboard_later, get_clipboard_text, set_clipboard_text
    from .config import Config, ConfigError, load_config
    from .hotkey import register_push_to_talk
    from .pipeline import VoicePipeline
    from .recorder import MicRecorder
    from .terms import TermsError, load_terms

    config_path = os.path.join(BASE_DIR, "config.yaml")
    terms_path = os.path.join(BASE_DIR, "terms.yaml")
    model_dir = os.path.join(BASE_DIR, "models", "sensevoice")

    try:
        config = load_config(config_path)
        rules = load_terms(terms_path)
    except (ConfigError, TermsError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        return 1

    try:
        engine = ASREngine.load(model_dir)
    except (ModelError, DependencyMissingError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        return 1

    def restore(original):
        restore_clipboard_later(original, config.restore_delay_sec)

    pipeline = VoicePipeline(
        config=config,
        recorder=MicRecorder(config.sample_rate),
        engine=engine,
        rules=rules,
        clipboard_get=get_clipboard_text,
        clipboard_set=set_clipboard_text,
        paste=make_paste(),
        restore=restore,
        beep=make_beep(config.beep),
    )

    print(f"voice-input 就绪：按住 {config.hotkey} 说话，松开粘贴。Ctrl+C 退出。")
    try:
        register_push_to_talk(config.hotkey, pipeline.on_press, pipeline.on_release)
    except KeyboardInterrupt:
        print("\n退出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`app/selftest.py`：

```python
"""端到端自检：录 2 秒 → 识别 → 打印（不写剪贴板、不粘贴）。"""
from __future__ import annotations

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    from .asr import ASREngine, DependencyMissingError, ModelError
    from .config import load_config
    from .recorder import MicRecorder
    from .terms import load_terms

    config = load_config(os.path.join(BASE_DIR, "config.yaml"))
    rules = load_terms(os.path.join(BASE_DIR, "terms.yaml"))
    model_dir = os.path.join(BASE_DIR, "models", "sensevoice")

    try:
        engine = ASREngine.load(model_dir)
    except (ModelError, DependencyMissingError) as exc:
        print(f"[自检失败] {exc}", file=sys.stderr)
        return 1

    rec = MicRecorder(config.sample_rate)
    print("自检：请对着麦克风说话，录制 2 秒…")
    rec.start()
    time.sleep(2.0)
    pcm = rec.stop()
    print(f"已录制 {len(pcm) / 2 / config.sample_rate:.2f} 秒，识别中…")
    text = engine.transcribe(pcm)
    from .terms import apply_terms

    text = apply_terms(text, rules)
    print(f"识别结果: {text!r}")
    print("自检通过。" if text.strip() else "自检完成但识别为空：请检查麦克风默认设备。")
    return 0 if text.strip() else 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: 语法级验证（本机无硬件依赖，仅确认可导入装配模块不炸）**

Run: `python -c "import app.main, app.selftest, app.hotkey"`
Expected: 无输出（导入成功）

Run: `python -m unittest discover -s tests -v`
Expected: 43 tests OK

- [ ] **Step 7: Commit**

```bash
git add app tests
git commit -m "feat: 热键匹配/注册与 main/selftest 装配"
```

---

### Task 8: 默认配置文件、启动脚本、.gitignore

**Files:**
- Create: `config.yaml`
- Create: `terms.yaml`
- Create: `start-voice-input.bat`
- Create: `.gitignore`

**Interfaces:**
- Consumes: Task 1/2 的文件格式
- Produces: 默认配置与启动入口（`start-voice-input.bat` 找 `runtime\python.exe`，不存在则提示先运行 install.bat）

- [ ] **Step 1: 写文件**

`config.yaml`：

```yaml
# voice-input 配置。热键格式见 README；修改后重启生效。
hotkey: ctrl+shift+space
auto_paste: true          # false 时仅写剪贴板，不模拟 Ctrl+V
restore_clipboard: true   # 粘贴后恢复原剪贴板文本
restore_delay_sec: 1.5
beep: true
min_duration_ms: 300      # 短于该时长的按住视为误触
sample_rate: 16000
```

`terms.yaml`：

```yaml
# 术语纠正表：按顺序替换，先匹配先得。regex: true 时 pattern 为正则。
rules:
  - pattern: 斯布林
    replacement: Spring
  - pattern: 买八提寺
    replacement: MyBatis
  - pattern: 斯波瑞特
    replacement: Spirit
  - pattern: 迈文克
    replacement: Maven
  - pattern: 格拉德
    replacement: Gradle
  - pattern: 道克
    replacement: Docker
  - pattern: (?i)open\s*code\s*desktop
    replacement: OpenCode Desktop
    regex: true
```

`start-voice-input.bat`：

```bat
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
```

`.gitignore`：

```
__pycache__/
*.pyc
models/
runtime/
*.zip
.pytest_cache/
```

- [ ] **Step 2: 验证配置文件可被加载**

Run: `python -c "from app.config import load_config; from app.terms import load_terms; c=load_config('config.yaml'); r=load_terms('terms.yaml'); print(c.hotkey, len(r))"`
Expected: `ctrl+shift+space 7`

- [ ] **Step 3: Commit**

```bash
git add config.yaml terms.yaml start-voice-input.bat .gitignore
git commit -m "feat: 默认配置/术语表与启动脚本"
```

---

### Task 9: 打包机构建脚本 + README（打包机指南）

**Files:**
- Create: `build/packages.txt`
- Create: `build/build-offline.ps1`
- Modify: `README.md`（新建，先写打包机部分）

**Interfaces:**
- Consumes: `app/`、`config.yaml`、`terms.yaml`、`install.bat`（Task 10 创建，脚本里引用）
- Produces: `build\dist\voice-input-offline-<yyyyMMdd>.zip`，内含：`app\`、`tests\`、`build\`、`config.yaml`、`terms.yaml`、`install.bat`、`start-voice-input.bat`、`README.md`、`models\sensevoice\`、`runtime.zip`

- [ ] **Step 1: 写 packages.txt**

```
funasr-onnx
onnxruntime
keyboard
sounddevice
numpy
pyyaml
pytest
modelscope
conda-pack
```

（注：conda-pack 也入环境，方便脚本直接调用；modelscope 仅用于下载模型，随包带走无害。）

- [ ] **Step 2: 写 build-offline.ps1**

```powershell
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
& $pyExe -m conda_pack -n $envName -o (Join-Path $PSScriptRoot "runtime.zip") --force
if ($LASTEXITCODE -ne 0) { throw "conda-pack 失败" }

Write-Host "[6/6] 组装离线包…"
$dist = Join-Path $PSScriptRoot "dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null
$stage = Join-Path $dist "voice-input"
New-Item -ItemType Directory -Path $stage | Out-Null

$items = @("app", "tests", "build", "config.yaml", "terms.yaml",
           "start-voice-input.bat", ".gitignore")
foreach ($item in $items) {
    Copy-Item (Join-Path $projectRoot $item) -Destination $stage -Recurse
}
Copy-Item (Join-Path $projectRoot "install.bat") -Destination $stage -ErrorAction SilentlyContinue
Copy-Item (Join-Path $projectRoot "README.md") -Destination $stage -ErrorAction SilentlyContinue
Copy-Item (Join-Path $projectRoot "models") -Destination $stage -Recurse
Copy-Item (Join-Path $PSScriptRoot "runtime.zip") -Destination $stage

$zip = Join-Path $dist ("voice-input-offline-{0}.zip" -f (Get-Date -Format "yyyyMMdd"))
Compress-Archive -Path $stage -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force
Remove-Item (Join-Path $PSScriptRoot "runtime.zip") -Force

Write-Host "完成: $zip"
Write-Host "请将此 zip 拷贝到公司电脑并解压，运行 install.bat。"
```

- [ ] **Step 3: 写 README.md（打包机指南部分）**

`README.md`：

````markdown
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

## 已知限制

- 前台为管理员权限窗口时，热键拦截与模拟粘贴可能失效（UIPI），
  请以非管理员身份运行 OpenCode Desktop。
- 剪贴板恢复仅支持文本，图片/文件类型的剪贴板内容会被覆盖。
- 与 IDEA SmartType 补全（Ctrl+Shift+Space）冲突，可在 config.yaml 换热键。
````

- [ ] **Step 4: 验证 ps1 语法**

Run: `$null = [System.Management.Automation.Language.Parser]::ParseFile("C:\code\voice-input\build\build-offline.ps1", [ref]$null, [ref]$err); if ($err) { $err } else { "语法 OK" }`
Expected: `语法 OK`

- [ ] **Step 5: Commit**

```bash
git add build README.md
git commit -m "build: 离线包一键构建脚本与打包机指南"
```

---

### Task 10: install.bat + README 公司机指南

**Files:**
- Create: `install.bat`
- Modify: `README.md`（把「公司机指南」小节替换为完整内容）

**Interfaces:**
- Consumes: 离线包里的 `runtime.zip`
- Produces: `runtime\` 目录（含 python.exe）、桌面快捷方式、（可选）开机自启

- [ ] **Step 1: 写 install.bat**

```bat
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
```

- [ ] **Step 2: 更新 README.md 公司机指南**

把 README 中 `## 公司机指南` 小节及其下一行说明替换为：

````markdown
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
````

- [ ] **Step 3: 本机可验证的部分——快捷方式 PowerShell 命令试运行**

Run（在临时目录验证 COM 快捷方式创建逻辑，不动真桌面）：

```powershell
$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut("$env:TEMP\vi-test.lnk"); $lnk.TargetPath = "C:\code\voice-input\start-voice-input.bat"; $lnk.Save(); Test-Path "$env:TEMP\vi-test.lnk"; Remove-Item "$env:TEMP\vi-test.lnk"
```
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add install.bat README.md
git commit -m "build: 公司机一键安装脚本与部署指南"
```

---

### Task 11: 离线包就位后的真机验证（Phase 2 gate，非本机编码任务）

**Files:**
- 无新文件；验证发现的问题回改对应模块。

**Interfaces:**
- Consumes: Task 9 产出的离线包 + Task 10 的安装流程
- Produces: 验收结论（README 清单逐项打勾）

- [ ] **Step 1: 打包机执行 build-offline.ps1**，确认产出 zip 且单测全绿。
- [ ] **Step 2: 公司机解压 + install.bat**，确认单测全绿。
- [ ] **Step 3: `runtime\python.exe -m app.selftest`**，说中文+英文混合句（如“帮我用spring boot写个接口”），确认识别文本、标点、术语纠正。
  - 若 funasr_onnx 的模型文件名/SenseVoiceSmall 返回结构与 `app/asr.py` 预期不符（`REQUIRED_FILES`、`transcribe` 解包），在此步修正并回传打包机重新打包（或只改代码文件拷回）。
- [ ] **Step 4: 启动主程序**，在记事本验证：按住说话 → 松开 → 文本出现 + 1.5s 后剪贴板恢复。
- [ ] **Step 5: OpenCode Desktop 输入框重复 Step 4**，确认空格未透传输入框（热键拦截生效）。若 space 拦截失效，调整 `app/hotkey.py` 的 hook 策略（keyboard 库 `keyboard.hook(suppress=True)` + 返回 False 语义在 Windows 的实际行为）。
- [ ] **Step 6: README 手工验收清单逐项验证并打勾**（IDEA 冲突行为、微信/浏览器、terms.yaml 热改）。
- [ ] **Step 7: 验证发现的修复全部 commit**

```bash
git add -A
git commit -m "fix: 真机验证修正（asr/hotkey 细节按实测调整）"
```

---

## Self-Review 记录

- **Spec 覆盖**：spec 的配置项/术语表/错误处理/打包流程/安装流程/验收清单分别由 Task 1、2、6（错误分支）、9、10、11 承接；spec 中「pyperclip」按已批准偏差改为 ctypes（Task 3）。spec 目录中 `selftest.py` 在 Task 7，`clipboard.py` 行为一致。
- **占位符扫描**：无 TBD/TODO；funasr_onnx API 细节给了具体默认实现 + Task 11 Step 3 的核对-回改闭环。
- **类型一致性**：`VoicePipeline` 构造参数名在 Task 6 定义、Task 7 main.py 装配处逐字一致（`clipboard_get/clipboard_set/paste/restore/beep`）；`audio_duration_seconds(pcm, sample_rate)` 签名在 Task 4/6 一致；`load_config/load_terms` 签名在 Task 1/2/7/8 一致。
