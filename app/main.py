"""装配入口：配置 → 模型 → 管线 → 热键。"""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_beep(enabled: bool):
    import winsound

    def beep(kind: str) -> None:
        if not enabled:
            return
        if kind == "start":
            winsound.Beep(440, 80)
        elif kind == "done":
            winsound.Beep(880, 120)
        elif kind == "error":
            for _ in range(3):
                winsound.Beep(220, 60)

    return beep


def make_paste():
    import keyboard

    def paste() -> None:
        keyboard.send("ctrl+v")

    return paste


def main() -> int:
    from .asr import ASREngine, DependencyMissingError, ModelError
    from .clipboard import restore_clipboard_later, get_clipboard_text, set_clipboard_text
    from .config import Config, ConfigError, load_config
    from .hotkey import register_push_to_talk
    from .pipeline import VoicePipeline
    from .recorder import MicRecorder
    from .terms import TermsError, load_terms

    config_path = os.path.join(BASE_DIR, "config.yaml")
    terms_path = os.path.join(BASE_DIR, "terms.yaml")
    model_dir = os.path.join(BASE_DIR, "models", "sensevoice")

    try:
        config = load_config(config_path)
        rules = load_terms(terms_path)
    except (ConfigError, TermsError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        return 1

    try:
        engine = ASREngine.load(model_dir)
    except (ModelError, DependencyMissingError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        return 1

    def restore(original):
        restore_clipboard_later(original, config.restore_delay_sec)

    pipeline = VoicePipeline(
        config=config,
        recorder=MicRecorder(config.sample_rate),
        engine=engine,
        rules=rules,
        clipboard_get=get_clipboard_text,
        clipboard_set=set_clipboard_text,
        paste=make_paste(),
        restore=restore,
        beep=make_beep(config.beep),
    )

    print(f"voice-input 就绪：按住 {config.hotkey} 说话，松开粘贴。Ctrl+C 退出。")
    try:
        register_push_to_talk(config.hotkey, pipeline.on_press, pipeline.on_release)
    except KeyboardInterrupt:
        print("\n退出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
