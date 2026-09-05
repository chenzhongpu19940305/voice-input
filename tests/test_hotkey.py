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
