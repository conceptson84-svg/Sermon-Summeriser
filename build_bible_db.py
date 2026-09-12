#!/usr/bin/env python3
"""Build the bundled Bible SQLite from public-domain JSON sources.

Run this once (needs internet) before packaging, to produce
sermon_summarizer/bible/bible.sqlite. The app reads that file read-only at
runtime; if it's absent, live verse display simply disables itself.

    python build_bible_db.py

Sources are the getbible.net v2 JSON API: {"books": [{"nr", "name",
"chapters": [{"chapter", "verses": [{"verse", "text"}]}]}]} with the 66 books in
canonical order (book "nr" is 1-based), mapped to our canonical book names via
list(BOOK_CHAPTERS).

Only public-domain versions belong here. Copyrighted versions (NIV/ESV/NLT) are a
v2 online-fetch feature and must NOT be bundled.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sermon_summarizer.slides.scripture import BOOK_CHAPTERS  # noqa: E402
from sermon_summarizer.bible.lookup import DB_FILENAME  # noqa: E402

CANONICAL_BOOKS = list(BOOK_CHAPTERS)  # 66 books, canonical order

# version code (stored in DB) -> getbible.net v2 translation slug.
# All public-domain.
SOURCES = {
    "WEB": "web",            # World English Bible (modern, default)
    "KJV": "kjv",            # King James Version
    "ASV": "asv",            # American Standard Version
    "YLT": "ylt",            # Young's Literal Translation
    "BBE": "basicenglish",   # Bible in Basic English
    "DRA": "douayrheims",    # Douay-Rheims
}
BASE_URL = "https://api.getbible.net/v2/{slug}.json"

OUT_PATH = Path("sermon_summarizer/bible") / DB_FILENAME


def _fetch(slug: str) -> dict:
    url = BASE_URL.format(slug=slug)
    req = urllib.request.Request(url, headers={"User-Agent": "sermon-summarizer-build"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read().decode("utf-8-sig")
    return json.loads(data)


def _insert_version(conn, code: str, payload: dict) -> int:
    n = 0
    for book in payload.get("books", []):
        nr = book.get("nr")
        if not isinstance(nr, int) or not (1 <= nr <= len(CANONICAL_BOOKS)):
            continue
        canonical = CANONICAL_BOOKS[nr - 1]
        for chapter in book.get("chapters", []):
            ci = chapter.get("chapter")
            for v in chapter.get("verses", []):
                conn.execute(
                    "INSERT INTO verses(version, book, chapter, verse, text) VALUES (?,?,?,?,?)",
                    (code, canonical, ci, v.get("verse"), (v.get("text") or "").strip()),
                )
                n += 1
    return n


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        OUT_PATH.unlink()
    conn = sqlite3.connect(str(OUT_PATH))
    conn.execute(
        "CREATE TABLE verses (version TEXT, book TEXT, chapter INT, verse INT, text TEXT)"
    )
    total = 0
    for code, slug in SOURCES.items():
        try:
            print(f"Fetching {code} …")
            payload = _fetch(slug)
            count = _insert_version(conn, code, payload)
            total += count
            print(f"  {code}: {count} verses")
        except Exception as e:  # noqa: BLE001
            print(f"  {code}: FAILED ({e}) — skipping")
    conn.execute(
        "CREATE INDEX idx_ref ON verses(version, book, chapter, verse)"
    )
    conn.commit()
    conn.close()
    if total == 0:
        print("No verses inserted — check the SOURCES URLs.")
        return 1
    size_mb = OUT_PATH.stat().st_size / 1e6
    print(f"\nBuilt {OUT_PATH} — {total} verses, {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
