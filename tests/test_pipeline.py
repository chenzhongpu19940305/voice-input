import unittest

from app.config import Config
from app.pipeline import VoicePipeline
from app.terms import TermRule


class FakeRecorder:
    def __init__(self, pcm=b"\x00" * 32000):  # 默认 1 秒
        self.pcm = pcm
        self.started = 0

    def start(self):
        self.started += 1

    def stop(self):
        return self.pcm


class FakeEngine:
    def __init__(self, text="识别文本"):
        self.text = text

    def transcribe(self, pcm):
        return self.text


class BoomEngine:
    def transcribe(self, pcm):
        raise RuntimeError("asr failed")


class Harness:
    def __init__(self, config=None, recorder=None, engine=None, rules=None):
        self.config = config or Config()
        self.recorder = recorder or FakeRecorder()
        self.engine = engine or FakeEngine()
        self.rules = rules or []
        self.events = {"beeps": [], "pastes": 0, "restores": [], "sets": [], "originals": []}
        self.pipe = VoicePipeline(
            config=self.config,
            recorder=self.recorder,
            engine=self.engine,
            rules=self.rules,
            clipboard_get=lambda: "旧剪贴板",
            clipboard_set=self.events["sets"].append,
            paste=self._paste,
            restore=self.events["restores"].append,
            beep=self.events["beeps"].append,
        )

    def _paste(self):
        self.events["pastes"] += 1


class TestNormalFlow(unittest.TestCase):
    def test_press_release_full_cycle(self):
        h = Harness()
        h.pipe.on_press()
        self.assertEqual(h.pipe.state, "recording")
        self.assertEqual(h.events["beeps"], ["start"])
        self.assertEqual(h.recorder.started, 1)
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], ["识别文本"])
        self.assertEqual(h.events["pastes"], 1)
        self.assertEqual(h.events["restores"], ["旧剪贴板"])
        self.assertEqual(h.events["beeps"], ["start", "done"])

    def test_terms_applied(self):
        h = Harness(rules=[TermRule("识别", "RECOG")])
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["sets"], ["RECOG文本"])

    def test_auto_paste_off(self):
        h = Harness(config=Config(auto_paste=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["sets"], ["识别文本"])
        self.assertEqual(h.events["pastes"], 0)
        self.assertEqual(h.events["restores"], ["旧剪贴板"])

    def test_restore_off(self):
        h = Harness(config=Config(restore_clipboard=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["pastes"], 1)
        self.assertEqual(h.events["restores"], [])


class TestEdgeCases(unittest.TestCase):
    def test_too_short_dropped_silently(self):
        h = Harness(recorder=FakeRecorder(pcm=b"\x00" * 1600))  # 50ms < 300ms
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], [])
        self.assertEqual(h.events["beeps"], ["start"])  # 只有开始音

    def test_empty_text_error_beep_no_paste(self):
        h = Harness(engine=FakeEngine(text="   "))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["beeps"], ["start", "error"])
        self.assertEqual(h.events["sets"], [])
        self.assertEqual(h.events["pastes"], 0)

    def test_engine_exception_contained(self):
        h = Harness(engine=BoomEngine())
        h.pipe.on_press()
        h.pipe.on_release()  # 不应抛出
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["beeps"], ["start", "error"])

    def test_press_while_recording_ignored(self):
        h = Harness()
        h.pipe.on_press()
        h.pipe.on_press()
        self.assertEqual(h.recorder.started, 1)

    def test_press_while_recognizing_ignored(self):
        h = Harness()
        states = []

        class SlowEngine:
            def transcribe(self, pcm):
                states.append(h.pipe.state)
                return "慢结果"

        h.engine = SlowEngine()
        h.pipe = VoicePipeline(
            config=h.config, recorder=h.recorder, engine=h.engine, rules=[],
            clipboard_get=lambda: None, clipboard_set=lambda t: None,
            paste=lambda: None, restore=lambda o: None, beep=lambda k: None,
        )
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(states, ["recognizing"])
        # 完整周期后可再次触发
        h.pipe.on_press()
        self.assertEqual(h.pipe.state, "recording")

    def test_release_without_press_noop(self):
        h = Harness()
        h.pipe.on_release()
        self.assertEqual(h.pipe.state, "idle")
        self.assertEqual(h.events["sets"], [])

    def test_beep_off(self):
        h = Harness(config=Config(beep=False))
        h.pipe.on_press()
        h.pipe.on_release()
        self.assertEqual(h.events["beeps"], [])


if __name__ == "__main__":
    unittest.main()
