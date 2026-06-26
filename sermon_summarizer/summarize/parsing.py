"""Defensive parsing of Claude's response into validated Points.

Separated from the API client so it can be unit-tested without a network call
(tests/test_claude_parse.py). This is where issue #4 (scripture validation) and
the malformed-JSON resilience path (#5) live.
"""

from __future__ import annotations

import json
import re

from ..slides.deck import Point
from ..slides.scripture import validate_reference

# Claude is told to return raw JSON, but models sometimes wrap it in ```json
# fences or add a stray sentence. Strip the most common wrappers before parsing.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _extract_json_array(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    m = _FENCE_RE.search(raw)
    if m:
        raw = m.group(1)
    m = _ARRAY_RE.search(raw)
    if m:
        return m.group(0)
    return None


def parse_points(raw: str) -> list[Point]:
    """Parse a Claude response into a list of Points.

    Never raises. On any malformed input returns [] so the caller can simply
    skip the cycle and keep the last slide on screen. Invalid scripture
    references are dropped (the point stays, the bad reference is removed).
    """
    blob = _extract_json_array(raw)
    if blob is None:
        return []
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    points: list[Point] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("point")
        if not isinstance(text, str) or not text.strip():
            continue
        scripture_raw = item.get("scripture")
        scripture = None
        if isinstance(scripture_raw, str) and scripture_raw.strip():
            # Drop a mis-transcribed reference; keep the point itself.
            scripture = validate_reference(scripture_raw)
        points.append(Point(text=text.strip(), scripture=scripture))
    return points
