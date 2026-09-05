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


def make_event_handler(keys, on_press, on_release, is_pressed):
    """构造 keyboard 事件回调：armed 状态机 + 拦截决策（可测纯逻辑）。"""
    matcher = HotkeyMatcher(keys[:-1], keys[-1], is_pressed)
    armed = False

    def on_event(event):
        nonlocal armed
        if event.name != keys[-1]:
            return True
        if event.event_type == "down":
            if armed:
                return False  # 拦截 auto-repeat 与修饰键已松开的持续 down
            if matcher.matches(event.name):
                armed = True
                on_press()
                return False
            return True  # 无修饰键的普通空格（正常打字）放行
        if event.event_type == "up":
            if armed:
                armed = False
                on_release()
                return False
            return True
        return True

    return on_event


def register_push_to_talk(hotkey_str: str, on_press: Callable[[], None],
                          on_release: Callable[[], None]) -> None:
    """注册按住式全局热键并阻塞监听（keyboard 库，Windows）。

    suppress=True + 回调返回 False 拦截目标键事件（不透传给前台应用，
    避免空格进入 OpenCode Desktop 输入框）；返回 True 放行其他按键。
    拦截效果依赖 keyboard 库 Windows suppress 语义，真机验证见验证清单（Task 11）。
    """
    import keyboard  # 延迟导入：内网开发机无此库

    keys = parse_hotkey(hotkey_str)
    on_event = make_event_handler(keys, on_press, on_release, keyboard.is_pressed)
    keyboard.hook(on_event, suppress=True)
    keyboard.wait()  # 阻塞直到进程退出
