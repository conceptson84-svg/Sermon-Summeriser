"""Real-time verse detector.

Runs over each incoming transcript chunk (not the 5-minute summary cycle) so a
cited verse can be displayed within a few seconds. Keeps a small carryover of
the previous chunk's tail so a reference split across two chunks
("...Romans eight" / "twenty-eight...") is still caught, and debounces so the
same verse doesn't re-fire repeatedly.

Pure logic (parser + lookup are injected/looked up); no threads of its own — the
controller calls feed() from the transcription consumer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .lookup import BibleLookup, DEFAULT_VERSION, Verse
from .spoken_parser import find_references

# References at or above this confidence may auto-display; below it they still
# surface for manual approval (per the eng review decision).
AUTO_CONFIDENCE = 0.7
# Don't re-fire the same reference within this window (seconds).
DEBOUNCE_SECONDS = 90
# How many trailing characters of the previous chunk to prepend to the next.
CARRYOVER_CHARS = 60


@dataclass
class DetectedVerse:
    reference: str      # "Romans 8:28"
    text: str           # verse text
    version: str
    confidence: float
    high_confidence: bool


class VerseDetector:
    def __init__(self, lookup: BibleLookup | None = None,
                 version: str = DEFAULT_VERSION, clock=time.monotonic):
        self._lookup = lookup if lookup is not None else BibleLookup()
        self._version = version
        self._clock = clock
        self._carry = ""
        self._last_fired: dict[str, float] = {}

    @property
    def available(self) -> bool:
        return self._lookup.available

    def set_version(self, version: str) -> None:
        self._version = version

    def feed(self, chunk: str) -> list[DetectedVerse]:
        """Scan a new transcript chunk. Returns detected verses (deduped by the
        debounce window). Empty when the DB is unavailable or nothing is found."""
        if not self._lookup.available or not chunk or not chunk.strip():
            self._carry = (self._carry + " " + (chunk or "")).strip()[-CARRYOVER_CHARS:]
            return []

        text = (self._carry + " " + chunk).strip()
        self._carry = text[-CARRYOVER_CHARS:]

        out: list[DetectedVerse] = []
        now = self._clock()
        for ref in find_references(text):
            verse = self._resolve(ref)
            if verse is None:
                continue
            # Key + display reference come from the resolved verse so the shown
            # reference always matches the shown text.
            key = verse.reference()
            last = self._last_fired.get(key)
            if last is not None and (now - last) < DEBOUNCE_SECONDS:
                continue
            self._last_fired[key] = now
            out.append(DetectedVerse(
                reference=key,
                text=verse.text,
                version=verse.version,
                confidence=ref.confidence,
                high_confidence=ref.confidence >= AUTO_CONFIDENCE,
            ))
        return out

    def _resolve(self, ref) -> Verse | None:
        if ref.verse is not None:
            v = self._lookup.get_verse(ref.book, ref.chapter, ref.verse, self._version)
            if v is not None:
                return v
        # Chapter-only, or the exact verse is missing — anchor on verse 1.
        return self._lookup.get_first_verse(ref.book, ref.chapter, self._version)
