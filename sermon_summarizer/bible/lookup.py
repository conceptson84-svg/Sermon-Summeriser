"""Fast local verse lookup from the bundled SQLite Bible.

The DB (built by build_bible_db.py) has one table:
    verses(version TEXT, book TEXT, chapter INT, verse INT, text TEXT)
indexed on (version, book, chapter, verse). Lookup is sub-millisecond.

If the DB is missing (e.g. a build without it), BibleLookup.available is False
and lookups return None — the feature disables gracefully, the app still runs.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DB_FILENAME = "bible.sqlite"


def default_db_path() -> Path:
    """Locate bible.sqlite from source (package dir) and inside a PyInstaller
    bundle (which may unpack it at the root or under the package path)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for cand in (Path(base) / DB_FILENAME,
                     Path(base) / "sermon_summarizer" / "bible" / DB_FILENAME):
            if cand.exists():
                return cand
        return Path(base) / DB_FILENAME
    return Path(__file__).resolve().parent / DB_FILENAME

# Bundled public-domain versions. Keys are the codes stored in the DB.
BUNDLED_VERSIONS = {
    "WEB": "World English Bible",
    "KJV": "King James Version",
    "ASV": "American Standard Version",
    "YLT": "Young's Literal Translation",
    "BBE": "Bible in Basic English",
    "DRA": "Douay-Rheims",
}
DEFAULT_VERSION = "WEB"


@dataclass(frozen=True)
class Verse:
    version: str
    book: str
    chapter: int
    verse: int
    text: str

    def reference(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"


class BibleLookup:
    def __init__(self, db_path: str | Path | None = None):
        self._path = Path(db_path) if db_path else default_db_path()
        self._conn = None
        if self._path.exists():
            try:
                # read-only, shareable across the UI + detector threads
                self._conn = sqlite3.connect(
                    f"file:{self._path}?mode=ro", uri=True, check_same_thread=False)
            except sqlite3.Error as e:  # pragma: no cover
                log.warning("could not open bible DB: %s", e)
                self._conn = None
        else:
            log.info("bible DB not found at %s — verse lookup disabled", self._path)

    @property
    def available(self) -> bool:
        return self._conn is not None

    def versions(self) -> list[str]:
        if not self._conn:
            return []
        try:
            rows = self._conn.execute("SELECT DISTINCT version FROM verses").fetchall()
            return sorted(r[0] for r in rows)
        except sqlite3.Error:
            return []

    def get_verse(self, book: str, chapter: int, verse: int,
                  version: str = DEFAULT_VERSION) -> Verse | None:
        if not self._conn:
            return None
        try:
            row = self._conn.execute(
                "SELECT text FROM verses WHERE version=? AND book=? AND chapter=? AND verse=?",
                (version, book, chapter, verse),
            ).fetchone()
        except sqlite3.Error as e:  # pragma: no cover
            log.warning("verse lookup failed: %s", e)
            return None
        if row is None:
            return None
        return Verse(version=version, book=book, chapter=chapter, verse=verse, text=row[0])

    def get_first_verse(self, book: str, chapter: int,
                        version: str = DEFAULT_VERSION) -> Verse | None:
        """When only a chapter is cited, return verse 1 as the anchor."""
        return self.get_verse(book, chapter, 1, version)
