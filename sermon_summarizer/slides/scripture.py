"""Scripture reference validation.

The summariser (Claude) extracts biblical references from a LIVE, sometimes
mis-transcribed sermon. Before any reference reaches the big screen or the NDI
broadcast feed, it passes through here. Anything that is not a real book +
in-range chapter/verse is dropped, never displayed.

This is the safety net for issue #4 in the eng review: a mistranscribed
"Hesitations 3:16" must never appear on the broadcast.

Pure data + pure functions. No I/O. Fully unit-tested in tests/test_scripture.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Chapter counts per canonical book (Protestant 66-book canon).
# Verse-level ranges are intentionally NOT enforced — chapter count is enough
# to reject garbage while staying maintainable. Validating chapter existence
# already kills the "Hesitations 3:16" / "John 99:1" failure class.
BOOK_CHAPTERS: dict[str, int] = {
    # Old Testament
    "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36,
    "Deuteronomy": 34, "Joshua": 24, "Judges": 21, "Ruth": 4,
    "1 Samuel": 31, "2 Samuel": 24, "1 Kings": 22, "2 Kings": 25,
    "1 Chronicles": 29, "2 Chronicles": 36, "Ezra": 10, "Nehemiah": 13,
    "Esther": 10, "Job": 42, "Psalms": 150, "Proverbs": 31,
    "Ecclesiastes": 12, "Song of Solomon": 8, "Isaiah": 66, "Jeremiah": 52,
    "Lamentations": 5, "Ezekiel": 48, "Daniel": 12, "Hosea": 14,
    "Joel": 3, "Amos": 9, "Obadiah": 1, "Jonah": 4, "Micah": 7,
    "Nahum": 3, "Habakkuk": 3, "Zephaniah": 3, "Haggai": 2,
    "Zechariah": 14, "Malachi": 4,
    # New Testament
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28,
    "Romans": 16, "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6,
    "Ephesians": 6, "Philippians": 4, "Colossians": 4,
    "1 Thessalonians": 5, "2 Thessalonians": 3, "1 Timothy": 6,
    "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13, "James": 5,
    "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1,
    "Jude": 1, "Revelation": 22,
}

# Common abbreviations and alternate spellings a speech-to-text engine or
# Claude might emit. Maps to the canonical key in BOOK_CHAPTERS.
_ALIASES: dict[str, str] = {
    "gen": "Genesis", "ex": "Exodus", "exod": "Exodus", "lev": "Leviticus",
    "num": "Numbers", "deut": "Deuteronomy", "deu": "Deuteronomy",
    "josh": "Joshua", "judg": "Judges", "ps": "Psalms", "psalm": "Psalms",
    "prov": "Proverbs", "eccl": "Ecclesiastes", "song of songs": "Song of Solomon",
    "isa": "Isaiah", "jer": "Jeremiah", "lam": "Lamentations", "ezek": "Ezekiel",
    "dan": "Daniel", "hos": "Hosea", "obad": "Obadiah", "mic": "Micah",
    "nah": "Nahum", "hab": "Habakkuk", "zeph": "Zephaniah", "hag": "Haggai",
    "zech": "Zechariah", "mal": "Malachi",
    "matt": "Matthew", "mt": "Matthew", "mk": "Mark", "lk": "Luke",
    "jn": "John", "rom": "Romans",
    "1 cor": "1 Corinthians", "2 cor": "2 Corinthians", "gal": "Galatians",
    "eph": "Ephesians", "phil": "Philippians", "philip": "Philippians",
    "col": "Colossians", "1 thess": "1 Thessalonians", "2 thess": "2 Thessalonians",
    "1 tim": "1 Timothy", "2 tim": "2 Timothy", "phlm": "Philemon",
    "heb": "Hebrews", "jas": "James", "1 pet": "1 Peter", "2 pet": "2 Peter",
    "rev": "Revelation",
}

# "1John", "1 John", "i john", "first john" -> normalize the ordinal prefix.
_ORDINAL_WORDS = {"first": "1", "second": "2", "third": "3", "i": "1", "ii": "2", "iii": "3"}

# Matches "John 3:16", "1 Corinthians 13", "Psalm 23:1-6", "John 3:16-18".
_REF_RE = re.compile(
    r"^\s*(?P<book>(?:[1-3]\s*|first\s+|second\s+|third\s+|i{1,3}\s+)?[A-Za-z][A-Za-z ]*?)"
    r"\s+(?P<chapter>\d{1,3})"
    r"(?::(?P<verse>\d{1,3})(?:-\d{1,3})?)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Reference:
    book: str
    chapter: int
    verse: int | None = None

    def display(self) -> str:
        if self.verse is None:
            return f"{self.book} {self.chapter}"
        return f"{self.book} {self.chapter}:{self.verse}"


def _canonical_book(raw: str) -> str | None:
    """Resolve a raw book token to a canonical book name, or None if unknown."""
    token = " ".join(raw.strip().split()).lower()

    # Normalize a leading ordinal word ("first john" -> "1 john").
    parts = token.split(" ", 1)
    if parts[0] in _ORDINAL_WORDS and len(parts) == 2:
        token = f"{_ORDINAL_WORDS[parts[0]]} {parts[1]}"
    # Normalize "1john" (no space) -> "1 john".
    m = re.match(r"^([1-3])([a-z].*)$", token)
    if m:
        token = f"{m.group(1)} {m.group(2)}"

    # Exact canonical match (case-insensitive).
    for canonical in BOOK_CHAPTERS:
        if canonical.lower() == token:
            return canonical
    # Alias match.
    if token in _ALIASES:
        return _ALIASES[token]
    return None


def parse_reference(raw: str) -> Reference | None:
    """Parse a single reference string. Returns None if unparseable."""
    if not raw or not raw.strip():
        return None
    m = _REF_RE.match(raw)
    if not m:
        return None
    book = _canonical_book(m.group("book"))
    if book is None:
        return None
    chapter = int(m.group("chapter"))
    verse = int(m.group("verse")) if m.group("verse") else None
    return Reference(book=book, chapter=chapter, verse=verse)


def is_valid_reference(raw: str) -> bool:
    """True only if raw names a real book and an in-range chapter."""
    ref = parse_reference(raw)
    if ref is None:
        return False
    return 1 <= ref.chapter <= BOOK_CHAPTERS[ref.book]


def validate_reference(raw: str) -> str | None:
    """Return the normalized display string if valid, else None (drop it).

    This is the single entry point the slide pipeline calls. A None return
    means: do not put this on the screen.
    """
    ref = parse_reference(raw)
    if ref is None:
        return None
    if not (1 <= ref.chapter <= BOOK_CHAPTERS[ref.book]):
        return None
    return ref.display()
