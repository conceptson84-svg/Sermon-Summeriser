"""Spoken-reference parser tests — the critical surface for live verse display."""

from sermon_summarizer.bible.spoken_parser import (
    find_references, _spoken_numbers_to_ints,
)


def _first(text):
    refs = find_references(text)
    return refs[0] if refs else None


# --- number-word conversion -------------------------------------------------

def test_number_groups():
    assert _spoken_numbers_to_ints(["three", "sixteen"]) == [3, 16]
    assert _spoken_numbers_to_ints(["eight", "twenty", "eight"]) == [8, 28]
    assert _spoken_numbers_to_ints(["twenty", "three"]) == [23]
    assert _spoken_numbers_to_ints(["twenty", "eight"]) == [28]
    assert _spoken_numbers_to_ints(["sixteen"]) == [16]
    assert _spoken_numbers_to_ints(["one", "hundred", "nineteen"]) == [119]


# --- spoken references ------------------------------------------------------

def test_spoken_chapter_verse():
    r = _first("turn with me to John three sixteen")
    assert r.reference() == "John 3:16"


def test_spoken_with_keywords():
    r = _first("open to John chapter three verse sixteen")
    assert r.reference() == "John 3:16"
    assert r.confidence >= 0.9


def test_numbered_book_spoken():
    r = _first("look at first Corinthians thirteen")
    assert r.reference() == "1 Corinthians 13"


def test_second_timothy():
    r = _first("second Timothy three verse sixteen tells us")
    assert r.reference() == "2 Timothy 3:16"


def test_romans_eight_twenty_eight():
    r = _first("Romans eight twenty-eight says all things work together")
    assert r.reference() == "Romans 8:28"


def test_psalm_chapter_only():
    r = _first("let us read Psalm twenty three")
    assert r.book == "Psalms" and r.chapter == 23 and r.verse is None


# --- written form embedded in speech ---------------------------------------

def test_written_form():
    r = _first("as John 3:16 says")
    assert r.reference() == "John 3:16"
    assert r.confidence == 1.0


def test_written_chapter_only():
    r = _first("we are in Romans 8 today")
    assert r.book == "Romans" and r.chapter == 8


# --- confidence gating ------------------------------------------------------

def test_chapter_only_is_lower_confidence():
    r = _first("Psalm twenty three")
    assert r.confidence < 0.7  # ambiguous, should go to manual in auto mode


def test_full_ref_is_high_confidence():
    r = _first("John chapter three verse sixteen")
    assert r.confidence >= 0.9


# --- rejection / false positives -------------------------------------------

def test_rejects_out_of_range_chapter():
    # Jude has 1 chapter; "Jude five" is invalid.
    assert _first("Jude five") is None


def test_rejects_non_reference_numbers():
    # No book name -> no reference.
    assert find_references("I said it three or four times to sixteen people") == []


def test_empty_text():
    assert find_references("") == []
    assert find_references("   ") == []


def test_multiple_references_in_one_chunk():
    refs = find_references("compare John 3:16 with Romans eight twenty-eight")
    got = {r.reference() for r in refs}
    assert "John 3:16" in got
    assert "Romans 8:28" in got
