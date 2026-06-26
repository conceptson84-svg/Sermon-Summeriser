"""Rolling transcript window.

Keeps roughly the last N minutes of transcribed text. Every summarisation cycle
reads the window; Claude extracts only what's NEW (the deck dedupes repeats).
Pure logic, unit-tested in tests/test_window.py.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class _Segment:
    ts: float
    text: str


class TranscriptWindow:
    def __init__(self, window_seconds: float = 300.0, clock=time.monotonic):
        self._window = window_seconds
        self._clock = clock
        self._segments: "deque[_Segment]" = deque()

    def set_window_seconds(self, seconds: float) -> None:
        """Change how much recent speech is kept. Takes effect immediately."""
        self._window = float(seconds)
        self._evict()

    def add(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._segments.append(_Segment(ts=self._clock(), text=text))
        self._evict()

    def _evict(self) -> None:
        cutoff = self._clock() - self._window
        while self._segments and self._segments[0].ts < cutoff:
            self._segments.popleft()

    def text(self) -> str:
        self._evict()
        return " ".join(s.text for s in self._segments).strip()

    def clear(self) -> None:
        self._segments.clear()

    def __len__(self) -> int:
        self._evict()
        return len(self._segments)
