import os
import tempfile
import unittest

from app.config import Config, ConfigError, load_config


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(os.path.join(d, "nope.yaml"))
        self.assertEqual(cfg.hotkey, "ctrl+shift+space")
        self.assertTrue(cfg.auto_paste)
        self.assertTrue(cfg.restore_clipboard)
        self.assertEqual(cfg.restore_delay_sec, 1.5)
        self.assertTrue(cfg.beep)
        self.assertEqual(cfg.min_duration_ms, 300)
        self.assertEqual(cfg.sample_rate, 16000)

    def test_partial_file_keeps_defaults_for_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("hotkey: ctrl+shift+d\nbeep: false\n")
            cfg = load_config(p)
        self.assertEqual(cfg.hotkey, "ctrl+shift+d")
        self.assertFalse(cfg.beep)
        self.assertTrue(cfg.auto_paste)

    def test_full_file_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "hotkey: ctrl+alt+v\n"
                    "auto_paste: false\n"
                    "restore_clipboard: false\n"
                    "restore_delay_sec: 2.0\n"
                    "beep: false\n"
                    "min_duration_ms: 500\n"
                    "sample_rate: 16000\n"
                )
            cfg = load_config(p)
        self.assertEqual(cfg.hotkey, "ctrl+alt+v")
        self.assertFalse(cfg.auto_paste)
        self.assertFalse(cfg.restore_clipboard)
        self.assertEqual(cfg.restore_delay_sec, 2.0)
        self.assertEqual(cfg.min_duration_ms, 500)

    def test_bad_type_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("min_duration_ms: abc\n")
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_broken_yaml_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(":\n  - [broken\n")
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_gbk_file_raises_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.yaml")
            with open(p, "wb") as f:
                f.write("hotkey: 中文热键\n".encode("gbk"))
            with self.assertRaises(ConfigError):
                load_config(p)


if __name__ == "__main__":
    unittest.main()
