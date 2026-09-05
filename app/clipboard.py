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
