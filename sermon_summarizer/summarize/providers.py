"""LLM provider adapters.

The summariser only needs one operation from a model: given a system prompt and
a user prompt, return raw text. Everything downstream (parse_points, scripture
validation, deck) is provider-agnostic, so adding a provider is just adding a
client that implements `complete()`.

Two adapters cover every provider we care about:

  * AnthropicClient        — Claude, via the native anthropic SDK.
  * OpenAICompatibleClient — OpenRouter, OpenAI, DeepSeek, and Gemini, all of
                             which expose an OpenAI-compatible /chat/completions
                             endpoint. Only base_url + model differ.

Pick a provider in config.json with `provider` + `model` + the matching key.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)

# Default base URLs for the OpenAI-compatible providers. Anthropic is handled
# separately by its native SDK.
PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

# Sensible default model per provider when config leaves `model` blank.
PROVIDER_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openrouter": "anthropic/claude-haiku-4.5",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-2.0-flash",
}

SUPPORTED_PROVIDERS = ("anthropic",) + tuple(PROVIDER_BASE_URLS)


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return raw model text. May raise — the Summarizer wraps this."""
        ...


class ProviderError(Exception):
    """Construction-time error (missing SDK / key / unknown provider)."""


class AnthropicClient:
    def __init__(self, api_key: str, model: str, timeout: float = 30.0, max_tokens: int = 512):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - env dependent
            raise ProviderError("anthropic SDK not installed. Run: pip install anthropic") from e
        if not api_key:
            raise ProviderError("No Anthropic API key provided.")
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover - network
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )


class OpenAICompatibleClient:
    """Works for OpenRouter, OpenAI, DeepSeek, and Gemini (OpenAI-compat endpoint)."""

    def __init__(self, api_key: str, model: str, base_url: str,
                 timeout: float = 30.0, max_tokens: int = 512):
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - env dependent
            raise ProviderError("openai SDK not installed. Run: pip install openai") from e
        if not api_key:
            raise ProviderError("No API key provided for OpenAI-compatible provider.")
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover - network
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or ""


def build_client(config) -> LLMClient:
    """Construct the right client from config. Raises ProviderError on bad config."""
    provider = (getattr(config, "provider", None) or "anthropic").lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    model = getattr(config, "model", "") or PROVIDER_DEFAULT_MODELS[provider]
    api_key = _resolve_key(config, provider)

    if provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model)

    base_url = getattr(config, "base_url", "") or PROVIDER_BASE_URLS[provider]
    return OpenAICompatibleClient(api_key=api_key, model=model, base_url=base_url)


def _resolve_key(config, provider: str) -> str:
    """Pick the API key: a provider-specific key if set, else the generic one."""
    # e.g. provider 'gemini' -> config.gemini_api_key, falling back to api_key.
    specific = getattr(config, f"{provider}_api_key", "") or ""
    if specific:
        return specific
    # Back-compat: anthropic_api_key was the original field name.
    if provider == "anthropic":
        legacy = getattr(config, "anthropic_api_key", "") or ""
        if legacy:
            return legacy
    return getattr(config, "api_key", "") or ""
