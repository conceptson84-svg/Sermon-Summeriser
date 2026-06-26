"""Rolling transcript window tests."""

from sermon_summarizer.transcribe.window import TranscriptWindow


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_accumulates_text():
    w = TranscriptWindow(window_seconds=300, clock=FakeClock())
    w.add("first")
    w.add("second")
    assert w.text() == "first second"


def test_evicts_old_segments():
    clk = FakeClock()
    w = TranscriptWindow(window_seconds=60, clock=clk)
    w.add("old")
    clk.t = 120.0
    w.add("new")
    assert w.text() == "new"


def test_ignores_blank():
    w = TranscriptWindow(clock=FakeClock())
    w.add("")
    w.add("   ")
    assert len(w) == 0


def test_clear():
    w = TranscriptWindow(clock=FakeClock())
    w.add("text")
    w.clear()
    assert w.text() == ""
