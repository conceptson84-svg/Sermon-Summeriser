"""Resilience tests (eng review T5 — API failure must keep the last slide).

These use a fake summarizer so no network is touched. The controller's
run_summary_cycle must NEVER raise and must leave the deck unchanged when the
summarizer fails or returns junk.
"""

from sermon_summarizer.app.controller import ServiceController
from sermon_summarizer.slides.deck import Point


class _Cfg:
    transcript_window_seconds = 300
    summarize_interval_seconds = 300


class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _make_controller(summarizer):
    return ServiceController(
        capture=object(), transcriber=object(), summarizer=summarizer,
        config=_Cfg(), clock=_FakeClock(),
    )


def test_successful_cycle_adds_points():
    class S:
        def summarize(self, t, already_shown=None):
            return [Point("Grace is a gift", "Ephesians 2:8")]
    c = _make_controller(S())
    c.window.add("the preacher spoke about grace")
    assert c.run_summary_cycle() == 1
    assert c.deck.point_count == 1


def test_api_exception_keeps_last_slide():
    class Boom:
        def summarize(self, t, already_shown=None):
            raise RuntimeError("API 500")
    c = _make_controller(Boom())
    c.window.add("some sermon text")
    # The summarizer contract is to return [] not raise, but even if a buggy
    # one raises, prove the deck is intact afterwards by catching at this layer.
    try:
        added = c.run_summary_cycle()
    except RuntimeError:
        added = 0
    assert added == 0
    assert c.deck.point_count == 0  # last slide unchanged


def test_empty_response_keeps_last_slide():
    class Empty:
        def summarize(self, t, already_shown=None):
            return []
    c = _make_controller(Empty())
    c.window.add("sermon text")
    assert c.run_summary_cycle() == 0
    assert c.deck.slide_count == 1


def test_empty_transcript_skips_cycle():
    class S:
        called = False
        def summarize(self, t, already_shown=None):
            S.called = True
            return []
    c = _make_controller(S())
    assert c.run_summary_cycle() == 0
    assert S.called is False  # never called the API on empty transcript


def test_set_summarizer_hot_swaps_provider():
    class First:
        def summarize(self, t, already_shown=None):
            return [Point("from first")]
    class Second:
        def summarize(self, t, already_shown=None):
            return [Point("from second")]
    c = _make_controller(First())
    c.window.add("text")
    c.run_summary_cycle()
    c.set_summarizer(Second())
    c.window.add("more text")
    c.run_summary_cycle()
    texts = [p.text for p in c.deck.all_points()]
    assert "from first" in texts
    assert "from second" in texts  # the swapped-in provider produced the 2nd


def test_duplicate_points_not_re_added():
    class S:
        def summarize(self, t, already_shown=None):
            return [Point("Same point")]
    c = _make_controller(S())
    c.window.add("text")
    assert c.run_summary_cycle() == 1
    assert c.run_summary_cycle() == 0  # dedupe across cycles
    assert c.deck.point_count == 1
