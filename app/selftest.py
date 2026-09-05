"""端到端自检：录 2 秒 → 识别 → 打印（不写剪贴板、不粘贴）。"""
from __future__ import annotations

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    from .asr import ASREngine, DependencyMissingError, ModelError
    from .config import load_config
    from .recorder import MicRecorder
    from .terms import apply_terms, load_terms

    config = load_config(os.path.join(BASE_DIR, "config.yaml"))
    rules = load_terms(os.path.join(BASE_DIR, "terms.yaml"))
    model_dir = os.path.join(BASE_DIR, "models", "sensevoice")

    try:
        engine = ASREngine.load(model_dir)
    except (ModelError, DependencyMissingError) as exc:
        print(f"[自检失败] {exc}", file=sys.stderr)
        return 1

    rec = MicRecorder(config.sample_rate)
    print("自检：请对着麦克风说话，录制 2 秒…")
    rec.start()
    time.sleep(2.0)
    pcm = rec.stop()
    print(f"已录制 {len(pcm) / 2 / config.sample_rate:.2f} 秒，识别中…")
    text = engine.transcribe(pcm)
    text = apply_terms(text, rules)
    print(f"识别结果: {text!r}")
    print("自检通过。" if text.strip() else "自检完成但识别为空：请检查麦克风默认设备。")
    return 0 if text.strip() else 2


if __name__ == "__main__":
    sys.exit(main())
