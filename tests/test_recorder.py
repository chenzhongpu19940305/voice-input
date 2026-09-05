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

    def test_start_failure_rolls_back_state(self):
        import sys
        import types

        fake_sd = types.ModuleType("sounddevice")

        class BoomStream:
            def __init__(self, **kw):
                pass

            def start(self):
                raise OSError("no device")

            def close(self):
                pass

        fake_sd.InputStream = BoomStream
        sys.modules["sounddevice"] = fake_sd
        try:
            rec = MicRecorder()
            with self.assertRaises(OSError):
                rec.start()
            self.assertFalse(rec.recording)
            self.assertIsNone(rec._stream)
            # 回滚后可再次尝试 start（不会因坏状态卡死）
        finally:
            del sys.modules["sounddevice"]


if __name__ == "__main__":
    unittest.main()
