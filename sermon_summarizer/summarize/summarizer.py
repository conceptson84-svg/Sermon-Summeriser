"""Provider-agnostic summariser.

Wraps any LLMClient (Claude, OpenRouter, Gemini, DeepSeek, ...) and keeps the
resilience contract from the eng review: summarize() NEVER raises. On API error,
timeout, rate limit, or malformed output it returns [], and the caller keeps the
last slide on screen.

The provider is chosen in config; this class doesn't know or care which one.
"""

from __future__ import annotations

import logging

from .parsing import parse_points
from .prompt import SYSTEM_PROMPT, build_user_prompt
from .providers import build_client
from ..slides.deck import Point

log = logging.getLogger(__name__)


class NullSummarizer:
    """Placeholder used when no API key is set yet. Returns nothing so the app
    runs; replaced via controller.set_summarizer once a key is entered."""

    def summarize(self, transcript: str, already_shown=None):
        return []


class Summarizer:
    def __init__(self, client):
        self._client = client

    @classmethod
    def from_config(cls, config) -> "Summarizer":
        return cls(build_client(config))

    def summarize(self, transcript: str, already_shown: list[str] | None = None) -> list[Point]:
        """Summarise the rolling transcript into validated Points.

        `already_shown` is the list of point texts already on the deck so the
        model can avoid restating them. Returns [] on empty input or ANY
        provider failure — never raises.
        """
        if not transcript or not transcript.strip():
            return []
        try:
            # Pass the already-shown points down so the prompt can dedupe them.
            prompt = build_user_prompt(transcript, already_shown=already_shown)
            text = self._client.complete(SYSTEM_PROMPT, prompt)
            return parse_points(text)
        except Exception as e:  # noqa: BLE001 - intentional: never crash the service
            log.warning("Summarize cycle failed, keeping last slide: %s", e)
            return []
