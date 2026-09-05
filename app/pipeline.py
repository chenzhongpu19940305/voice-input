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
        try:
            if self._config.beep:
                self._beep("start")
            self._recorder.start()
        except Exception:
            with self._lock:
                self._state = "idle"
            if self._config.beep:
                self._beep("error")

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
