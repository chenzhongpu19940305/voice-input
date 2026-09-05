"""全局热键：parse 纯逻辑可测；注册用 keyboard 库（延迟导入，双通道极性无关）。"""
from __future__ import annotations

from typing import Callable


def parse_hotkey(hotkey_str: str) -> list:
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    if not hotkey_str.strip() or any(not p for p in parts):
        raise ValueError(f"非法热键表达式: {hotkey_str!r}")
    return parts


def register_push_to_talk(hotkey_str: str, on_press: Callable[[], None],
                          on_release: Callable[[], None]) -> None:
    """注册按住式全局热键并阻塞监听（keyboard 库，Windows）。

    双通道设计（不依赖 hook 回调返回值极性——该语义在无库环境无法核实）：
    1. add_hotkey(..., suppress=True)：组合键 down 的拦截交给库内建机制
       （官方文档化行为，任何返回值极性下都正确），同时触发 on_press。
       auto-repeat 重复触发由 armed 守卫与 pipeline 状态机防重入吸收。
    2. 观察 hook（无抑制）：只观察 trigger 键 up 事件流以触发 on_release；
       回调无返回值（None），在任何极性下都不参与拦截决策。

    回调派发到 daemon 线程：低级键盘钩子回调超时（约 300ms）会被系统
    静默摘钩，管线（识别可达秒级）绝不能内联执行。
    """
    import threading

    import keyboard  # 延迟导入：内网开发机无此库

    keys = parse_hotkey(hotkey_str)
    trigger = keys[-1]
    armed = threading.Event()

    def _dispatch(fn):
        threading.Thread(target=fn, daemon=True).start()

    def _press():
        if armed.is_set():
            return  # auto-repeat：armed 已置位，忽略
        armed.set()
        _dispatch(on_press)

    def _release():
        armed.clear()
        _dispatch(on_release)

    keyboard.add_hotkey(hotkey_str, _press, suppress=True)

    def _observe_up(event):
        if event.name == trigger and event.event_type == "up" and armed.is_set():
            _release()

    keyboard.hook(_observe_up)
    keyboard.wait()  # 阻塞直到进程退出
