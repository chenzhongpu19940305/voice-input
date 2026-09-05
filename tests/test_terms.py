import os
import tempfile
import unittest

from app.terms import TermRule, TermsError, apply_terms, load_terms


class TestLoadTerms(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_terms(os.path.join(d, "nope.yaml")), [])

    def test_no_rules_key_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("rules: []\n")
            self.assertEqual(load_terms(p), [])

    def test_load_rules(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "rules:\n"
                    "  - pattern: 斯布林\n"
                    "    replacement: Spring\n"
                    "  - pattern: (?i)spring boot\n"
                    "    replacement: Spring Boot\n"
                    "    regex: true\n"
                )
            rules = load_terms(p)
        self.assertEqual(rules[0], TermRule("斯布林", "Spring"))
        self.assertEqual(rules[1], TermRule("(?i)spring boot", "Spring Boot", regex=True))

    def test_bad_regex_raises_terms_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write(
                    "rules:\n"
                    "  - pattern: '[unclosed'\n"
                    "    replacement: X\n"
                    "    regex: true\n"
                )
            with self.assertRaises(TermsError):
                load_terms(p)

    def test_gbk_file_raises_terms_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "wb") as f:
                f.write("rules:\n  - pattern: 中文\n".encode("gbk"))
            with self.assertRaises(TermsError):
                load_terms(p)

    def test_non_mapping_top_level_raises_terms_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "terms.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("- just\n- a list\n")
            with self.assertRaises(TermsError):
                load_terms(p)


class TestApplyTerms(unittest.TestCase):
    def test_no_rules_passthrough(self):
        self.assertEqual(apply_terms("帮我看看斯布林", []), "帮我看看斯布林")

    def test_literal_replace(self):
        rules = [TermRule("斯布林", "Spring")]
        self.assertEqual(apply_terms("用斯布林写接口", rules), "用Spring写接口")

    def test_order_matters(self):
        rules = [
            TermRule("斯布林布特", "Spring Boot"),
            TermRule("斯布林", "Spring"),
        ]
        self.assertEqual(apply_terms("斯布林布特和斯布林", rules), "Spring Boot和Spring")

    def test_regex_replace(self):
        rules = [TermRule("(?i)spring\\s+boot", "Spring Boot", regex=True)]
        self.assertEqual(apply_terms("升级spring BOOT 到3", rules), "升级Spring Boot 到3")

    def test_mixed_rules(self):
        rules = [
            TermRule("买八提寺", "MyBatis"),
            TermRule("([a-z]+)\\s*boot", r"\1 Boot", regex=True),
        ]
        self.assertEqual(apply_terms("用买八提寺和springboot搭", rules), "用MyBatis和spring Boot搭")


if __name__ == "__main__":
    unittest.main()
