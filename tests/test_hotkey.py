import unittest

from app.hotkey import HotkeyMatcher, make_event_handler, parse_hotkey


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


class _Evt:
    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


class TestEventHandler(unittest.TestCase):
    def setUp(self):
        self.pressed = set()
        self.calls = []
        self.handler = make_event_handler(
            ["ctrl", "shift", "space"],
            lambda: self.calls.append("press"),
            lambda: self.calls.append("release"),
            lambda n: n in self.pressed,
        )

    def test_hold_with_auto_repeat_all_swallowed(self):
        self.pressed.update(["ctrl", "shift"])
        self.assertFalse(self.handler(_Evt("space", "down")))   # 触发
        self.assertFalse(self.handler(_Evt("space", "down")))   # auto-repeat
        self.assertFalse(self.handler(_Evt("space", "down")))   # auto-repeat
        self.assertFalse(self.handler(_Evt("space", "up")))     # 释放
        self.assertEqual(self.calls, ["press", "release"])

    def test_plain_space_without_mods_passes_through(self):
        self.assertTrue(self.handler(_Evt("space", "down")))    # 正常打字放行
        self.assertEqual(self.calls, [])

    def test_mods_released_while_holding_swallowed(self):
        self.pressed.update(["ctrl", "shift"])
        self.handler(_Evt("space", "down"))                     # armed
        self.pressed.clear()                                    # 松开修饰键
        self.assertFalse(self.handler(_Evt("space", "down")))   # 仍拦截
        self.assertFalse(self.handler(_Evt("space", "up")))
        self.assertEqual(self.calls, ["press", "release"])

    def test_other_keys_pass_through(self):
        self.assertTrue(self.handler(_Evt("v", "down")))

    def test_stray_up_passes_through(self):
        self.assertTrue(self.handler(_Evt("space", "up")))      # 未 armed 的 up 放行
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
