"""SenseVoice-Small ONNX 推理封装。依赖延迟导入，内网开发机可安全 import 本模块。"""
from __future__ import annotations

REQUIRED_FILES = (
    "model.integer.onnx",
    "chn_jpn_yue_eng_ko_spectok.bpe.txt",
)


class ModelError(Exception):
    """模型目录缺失或损坏。"""


class DependencyMissingError(Exception):
    """运行依赖未安装（离线包未解包/未 conda-unpack）。"""


def validate_model_dir(model_dir: str) -> list:
    """返回模型目录中缺失的必需文件名列表。"""
    import os

    return [name for name in REQUIRED_FILES if not os.path.isfile(os.path.join(model_dir, name))]


class ASREngine:
    def __init__(self, model, np):
        self._model = model
        self._np = np

    @classmethod
    def load(cls, model_dir: str) -> "ASREngine":
        missing = validate_model_dir(model_dir)
        if missing:
            raise ModelError(f"模型目录 {model_dir} 缺失文件: {missing}")
        try:
            import numpy as np
            from funasr_onnx import SenseVoiceSmall
        except ImportError as exc:
            raise DependencyMissingError(
                "推理依赖未安装（numpy/funasr_onnx），请确认离线包已解压并运行过 conda-unpack"
            ) from exc
        model = SenseVoiceSmall(model_dir, quantize=True)
        return cls(model, np)

    def transcribe(self, pcm: bytes) -> str:
        audio = self._np.frombuffer(pcm, dtype=self._np.int16).astype(self._np.float32) / 32768.0
        result = self._model(audio, fs=16000, language="auto", use_itn=True)
        if isinstance(result, list):
            result = result[0] if result else ""
        return str(result).strip()
