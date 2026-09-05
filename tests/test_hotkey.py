import unittest

from app.hotkey import parse_hotkey


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


if __name__ == "__main__":
    unittest.main()
