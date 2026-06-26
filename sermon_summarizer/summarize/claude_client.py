"""Back-compat shim.

The summariser is now provider-agnostic (see summarizer.Summarizer and
providers.build_client). This module is kept so existing imports of
ClaudeSummarizer keep working; new code should use Summarizer.from_config().
"""

from __future__ import annotations

from .providers import AnthropicClient, ProviderError as SummarizerError  # noqa: F401
from .summarizer import Summarizer

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ClaudeSummarizer(Summarizer):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 30.0):
        super().__init__(AnthropicClient(api_key=api_key, model=model, timeout=timeout))
