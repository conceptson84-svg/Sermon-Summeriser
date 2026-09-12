"""Parse spoken (and written) scripture references from live transcript text.

The preacher SAYS references, they aren't typed: "turn to Romans eight
twenty-eight", "first Corinthians thirteen", "John chapter three verse sixteen".
Whisper transcribes those as words, not "Romans 8:28". This module converts the
spoken form into a canonical reference plus a confidence score.

It reuses the book table / aliases / validator from slides.scripture — it does
NOT duplicate them. The confidence score lets the caller gate auto-display: a
shaky detection falls back to manual approval instead of hitting the broadcast.

Pure logic, no I/O. Heavily unit-tested in tests/test_spoken_parser.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..slides.scripture import BOOK_CHAPTERS, _canonical_book

_ONES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_TENS_VALUES = set(_TENS.values())
_NUMBER_WORDS = set(_ONES) | set(_TEENS) | set(_TENS) | {"hundred"}
# Filler words allowed between the book and its numbers without breaking parsing.
_FILLER = {"chapter", "chapters", "verse", "verses", "and", "vs", "v", "the"}

# Book names + aliases, longest first so "1 corinthians" wins over "corinthians".
_ORDINAL_PREFIX = {"first": "1", "second": "2", "third": "3"}


def _book_pattern() -> str:
    names = set()
    for canonical in BOOK_CHAPTERS:
        names.add(canonical.lower())
    # aliases are lowercase keys in scripture._ALIASES; include common spoken ones
    from ..slides.scripture import _ALIASES
    names.update(_ALIASES.keys())
    # allow spelled ordinals ("first john") and digit/roman ordinals
    variants = set()
    for n in names:
        variants.add(re.escape(n))
    # ordinal-word prefixed forms e.g. "first corinthians"
    for word in ("first", "second", "third"):
        for n in names:
            if n[0].isdigit():
                base = n[2:] if n[1] == " " else n[1:]
                variants.add(re.escape(f"{word} {base}"))
    # sort longest first for greedy matching
    return "|".join(sorted(variants, key=len, reverse=True))


_BOOK_RE = re.compile(r"\b(" + _book_pattern() + r")\b", re.IGNORECASE)
# Written form embedded in speech: "john 3:16", "1 corinthians 13:4-7"
_WRITTEN_NUM_RE = re.compile(r"^\s*(\d{1,3})(?::(\d{1,3}))?")


@dataclass(frozen=True)
class DetectedReference:
    book: str
    chapter: int
    verse: int | None
    confidence: float
    raw: str

    def reference(self) -> str:
        if self.verse is None:
            return f"{self.book} {self.chapter}"
        return f"{self.book} {self.chapter}:{self.verse}"


def _spoken_numbers_to_ints(words: list[str]) -> list[int]:
    """Convert a run of number words into the separate numbers they represent.
    "eight twenty eight" -> [8, 28] (chapter 8, verse 28);
    "twenty three" -> [23]; "three sixteen" -> [3, 16]."""
    result: list[int] = []
    current: int | None = None

    def flush():
        nonlocal current
        if current is not None:
            result.append(current)
            current = None

    for w in words:
        if w in _ONES:
            v = _ONES[w]
            if current is not None and current in _TENS_VALUES:
                current += v
                flush()
            elif current is not None and current >= 100 and current % 100 == 0:
                current += v
            else:
                # Keep as the current group — a following "hundred" may scale it.
                flush()
                current = v
        elif w in _TEENS:
            v = _TEENS[w]
            if current is not None and current >= 100 and current % 100 == 0:
                current += v
                flush()
            else:
                flush()
                current = v
                flush()
        elif w in _TENS:
            v = _TENS[w]
            if current is not None and current >= 100 and current % 100 == 0:
                current += v
            else:
                flush()
                current = v
        elif w == "hundred":
            if current is not None and current < 10:
                current *= 100
            else:
                current = (current or 1) * 100
        else:
            flush()
    flush()
    return result


def _normalize_book(raw: str) -> str | None:
    raw = raw.strip().lower()
    parts = raw.split(" ", 1)
    if parts[0] in _ORDINAL_PREFIX and len(parts) == 2:
        raw = f"{_ORDINAL_PREFIX[parts[0]]} {parts[1]}"
    return _canonical_book(raw)


def _parse_numbers_after(book: str, tail: str) -> tuple[int | None, int | None, float, bool]:
    """From the text right after a book name, extract (chapter, verse, confidence,
    explicit_written). Returns chapter=None if no number found."""
    # 1) Written form: "3:16" or "3"
    m = _WRITTEN_NUM_RE.match(tail)
    if m:
        chapter = int(m.group(1))
        verse = int(m.group(2)) if m.group(2) else None
        conf = 1.0 if verse is not None else 0.75
        return chapter, verse, conf, True

    # 2) Spoken form: collect number words + fillers, track verse keyword.
    tokens = re.findall(r"[a-z]+|\d+", tail.lower())
    num_words: list[str] = []
    verse_marker_at: int | None = None
    for tok in tokens[:10]:
        if tok in _NUMBER_WORDS:
            num_words.append(tok)
        elif tok.isdigit():
            num_words.append(_digit_to_word(tok))
        elif tok in ("verse", "verses"):
            verse_marker_at = len(num_words)
        elif tok in _FILLER:
            continue
        else:
            break
    if not num_words:
        return None, None, 0.0, False

    nums = _spoken_numbers_to_ints(num_words)
    if not nums:
        return None, None, 0.0, False
    if len(nums) == 1:
        # Only a chapter — ambiguous (could be missing verse). Medium confidence.
        return nums[0], None, 0.55, False
    chapter, verse = nums[0], nums[1]
    conf = 0.9 if verse_marker_at is not None else 0.7
    return chapter, verse, conf, False


_DIGIT_WORDS = {str(v): k for k, v in {**_ONES, **_TEENS, **_TENS}.items()}


def _digit_to_word(d: str) -> str:
    # Only used to keep small standalone digits in the spoken stream; multi-digit
    # numbers are handled by the written-form regex earlier.
    return _DIGIT_WORDS.get(d, d)


def find_references(text: str) -> list[DetectedReference]:
    """Scan a chunk of transcript text and return all detected references,
    validated against the canon. Invalid book/chapter combos are dropped."""
    if not text or not text.strip():
        return []
    out: list[DetectedReference] = []
    for m in _BOOK_RE.finditer(text):
        book = _normalize_book(m.group(1))
        if book is None:
            continue
        tail = text[m.end():m.end() + 60]
        chapter, verse, conf, _written = _parse_numbers_after(book, tail)
        if chapter is None:
            continue
        # Validate against the canon (reuse scripture's chapter counts).
        if not (1 <= chapter <= BOOK_CHAPTERS[book]):
            continue
        raw = text[m.start():m.end() + 20].strip()
        out.append(DetectedReference(book=book, chapter=chapter, verse=verse,
                                     confidence=conf, raw=raw))
    return out
