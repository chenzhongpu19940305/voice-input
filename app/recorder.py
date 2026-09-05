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

        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            callback=self._on_data,
        )
        with self._lock:
            self._buffer = bytearray()
        self._stream = stream
        self._recording = True  # 先置 flag 再 start，回调线程启动后即开始采集
        try:
            stream.start()
        except Exception:
            self._stream = None
            self._recording = False
            try:
                stream.close()
            except Exception:
                pass
            raise

    def stop(self) -> bytes:
        if not self._recording:
            raise RuntimeError("stop() 在未 start() 时调用")
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()  # close 返回后回调线程不再触发
            stream.close()
        self._recording = False  # 最后翻 flag：stop/close 期间到达的尾部回调仍被记录
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
