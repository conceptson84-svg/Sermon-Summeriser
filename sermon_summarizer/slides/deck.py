"""Rolling slide deck model.

The summariser adds one-liner key points over the course of a sermon. Rather
than overflow a single slide (issue #3 in the eng review), points roll onto a
new slide once the current one fills. The TV / NDI feed always shows the LATEST
slide; the full deck is what gets exported to PDF at the end.

Pure data model. No rendering, no I/O. Unit-tested in tests/test_deck.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_POINTS_PER_SLIDE = 6

# Near-duplicate detection. Two points whose meaningful-word overlap (Jaccard)
# is at or above this are treated as the same point reworded — the second is
# dropped. Set high enough that intentional emphasis with genuinely different
# words ("you are loved" vs "God treasures you") still gets through; the model
# handles the harder semantic cases via the already-on-screen list in the prompt.
SIMILARITY_THRESHOLD = 0.5

# Filler words ignored when comparing points for similarity.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "is",
    "are", "be", "was", "were", "you", "your", "his", "her", "its", "their",
    "our", "my", "we", "they", "he", "she", "it", "this", "that", "these",
    "those", "with", "as", "by", "at", "from", "into", "through", "not", "no",
    "will", "shall", "can", "has", "have", "had", "do", "does", "now", "today",
    "i", "me", "him", "them", "us", "who", "what", "which", "than", "then",
}


def _content_tokens(text: str) -> set[str]:
    """Meaningful words for similarity comparison: lowercased, de-punctuated,
    stopwords and very short tokens removed."""
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass(frozen=True)
class Point:
    """A single key point. `scripture` is an already-validated display string
    (or None). Validation happens upstream in scripture.validate_reference."""
    text: str
    scripture: str | None = None

    def key(self) -> str:
        """Dedupe key — same wording shouldn't be added twice across cycles."""
        return self.text.strip().lower()


@dataclass
class Slide:
    points: list[Point] = field(default_factory=list)

    @property
    def is_full(self) -> bool:
        return len(self.points) >= MAX_POINTS_PER_SLIDE


@dataclass
class Deck:
    """Append-only deck. New points flow onto the current slide until it fills,
    then a fresh slide starts. Exact duplicates and near-duplicates (the same
    point reworded) are ignored; genuinely distinct points are kept."""

    slides: list[Slide] = field(default_factory=lambda: [Slide()])
    similarity_threshold: float = SIMILARITY_THRESHOLD
    _seen: set[str] = field(default_factory=set)
    _token_sets: list[set[str]] = field(default_factory=list)

    @property
    def current(self) -> Slide:
        return self.slides[-1]

    def _is_near_duplicate(self, tokens: set[str]) -> bool:
        return any(
            _jaccard(tokens, existing) >= self.similarity_threshold
            for existing in self._token_sets
        )

    def add_point(self, point: Point, force: bool = False) -> bool:
        """Add a point. Returns False if it was an exact or near duplicate.
        With force=True (manual add by the operator) the dedupe checks are
        skipped so an intentional point is never silently dropped."""
        k = point.key()
        if not point.text.strip():
            return False
        tokens = _content_tokens(point.text)
        if not force:
            if k in self._seen:
                return False
            if tokens and self._is_near_duplicate(tokens):
                return False
        self._seen.add(k)
        self._token_sets.append(tokens)
        if self.current.is_full:
            self.slides.append(Slide())
        self.current.points.append(point)
        return True

    def add_points(self, points: list[Point]) -> int:
        """Add several points. Returns how many were actually added (non-dupe)."""
        return sum(1 for p in points if self.add_point(p))

    def latest_slide(self) -> Slide:
        """The slide currently shown on the TV / NDI feed."""
        return self.current

    def all_points(self) -> list[Point]:
        return [p for s in self.slides for p in s.points]

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    @property
    def point_count(self) -> int:
        return len(self._seen)
