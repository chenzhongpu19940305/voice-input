import os
import tempfile
import unittest

from app.asr import (
    REQUIRED_FILES,
    ASREngine,
    DependencyMissingError,
    ModelError,
    validate_model_dir,
)


class TestValidateModelDir(unittest.TestCase):
    def test_empty_dir_reports_all_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing = validate_model_dir(d)
        self.assertEqual(sorted(missing), sorted(REQUIRED_FILES))

    def test_missing_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            os.remove(os.path.join(d, REQUIRED_FILES[0]))
            missing = validate_model_dir(d)
        self.assertEqual(missing, [REQUIRED_FILES[0]])

    def test_complete_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            self.assertEqual(validate_model_dir(d), [])

    def test_nonexistent_dir_reports_all(self):
        self.assertEqual(sorted(validate_model_dir(r"C:\no\such\dir")), sorted(REQUIRED_FILES))


class TestASREngineLoad(unittest.TestCase):
    def test_load_missing_model_raises_model_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ModelError):
                ASREngine.load(d)

    def test_load_without_dependency_raises_dependency_missing(self):
        # 内网开发机没有 funasr_onnx：先造完整假模型目录再 load，
        # 期望被 DependencyMissingError 拦截而不是 ImportError 裸抛。
        # 若公司机装好依赖后此测试失败（真的 import 成功），标记 skip：
        try:
            import funasr_onnx  # noqa: F401

            self.skipTest("本机装有 funasr_onnx，跳过缺依赖分支")
        except ImportError:
            pass
        with tempfile.TemporaryDirectory() as d:
            for name in REQUIRED_FILES:
                open(os.path.join(d, name), "wb").close()
            with self.assertRaises(DependencyMissingError):
                ASREngine.load(d)


if __name__ == "__main__":
    unittest.main()
