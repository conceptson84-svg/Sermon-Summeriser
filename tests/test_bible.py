"""Lookup + detector tests. Skipped if the bundled DB isn't built."""

import pytest

from sermon_summarizer.bible.lookup import BibleLookup
from sermon_summarizer.bible.detector import VerseDetector

_lookup = BibleLookup()
needs_db = pytest.mark.skipif(not _lookup.available, reason="bible.sqlite not built")


@needs_db
def test_lookup_known_verse_all_versions():
    for v in ("WEB", "KJV", "ASV", "YLT", "BBE", "DRA"):
        verse = _lookup.get_verse("John", 3, 16, v)
        assert verse is not None and verse.text
        assert "God" in verse.text or "god" in verse.text.lower()


@needs_db
def test_lookup_unknown_returns_none():
    assert _lookup.get_verse("John", 999, 1) is None


@needs_db
def test_versions_lists_six():
    assert set(_lookup.versions()) == {"WEB", "KJV", "ASV", "YLT", "BBE", "DRA"}


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@needs_db
def test_detector_finds_spoken_verse():
    d = VerseDetector(lookup=_lookup, version="WEB", clock=_Clock())
    got = d.feed("as Romans eight twenty-eight tells us")
    assert len(got) == 1
    assert got[0].reference == "Romans 8:28"
    assert "work together" in got[0].text
    assert got[0].high_confidence is True


@needs_db
def test_detector_debounces_repeat():
    clk = _Clock()
    d = VerseDetector(lookup=_lookup, version="WEB", clock=clk)
    assert len(d.feed("John 3:16")) == 1
    assert len(d.feed("John 3:16 again")) == 0  # within debounce window
    clk.t = 200.0
    assert len(d.feed("John 3:16 once more")) == 1  # window passed


@needs_db
def test_detector_carryover_across_chunks():
    d = VerseDetector(lookup=_lookup, version="WEB", clock=_Clock())
    # Reference split across two chunks — carryover must join them.
    detected = []
    detected += d.feed("let us turn to Romans eight")
    detected += d.feed("twenty eight and read")
    refs = [g.reference for g in detected]
    assert "Romans 8:28" in refs


@needs_db
def test_detector_low_confidence_flagged():
    d = VerseDetector(lookup=_lookup, version="KJV", clock=_Clock())
    got = d.feed("let us read Psalm twenty three")
    assert len(got) == 1
    assert got[0].reference == "Psalms 23:1"
    assert got[0].high_confidence is False  # chapter-only -> manual in auto mode
