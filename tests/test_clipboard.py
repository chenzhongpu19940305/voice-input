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

    def test_set_failure_frees_handle(self):
        import ctypes
        from unittest import mock

        calls = []

        def fake_set_data(fmt, handle):
            calls.append(("set", handle))
            return 0  # 模拟 SetClipboardData 失败

        orig = clipboard.user32.SetClipboardData
        orig_free = clipboard.kernel32.GlobalFree
        clipboard.user32.SetClipboardData = fake_set_data
        clipboard.kernel32.GlobalFree = lambda h: calls.append(("free", h)) or 0
        try:
            with self.assertRaises(clipboard.CLIPBOARD_UNAVAILABLE):
                clipboard.set_clipboard_text("泄漏检查")
        finally:
            clipboard.user32.SetClipboardData = orig
            clipboard.kernel32.GlobalFree = orig_free
        frees = [c for c in calls if c[0] == "free"]
        self.assertEqual(len(frees), 1, "SetClipboardData 失败后必须 GlobalFree 恰好一次")


if __name__ == "__main__":
    unittest.main()
