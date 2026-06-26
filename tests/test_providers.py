"""Provider selection + multi-provider summariser tests.

No network: a fake client proves the Summarizer is provider-agnostic and keeps
the never-crash contract regardless of which provider is plugged in.
"""

import pytest

from sermon_summarizer.summarize.providers import (
    build_client, ProviderError, PROVIDER_BASE_URLS, PROVIDER_DEFAULT_MODELS,
)
from sermon_summarizer.summarize.summarizer import Summarizer


class Cfg:
    """Minimal config stand-in."""
    def __init__(self, **kw):
        self.provider = "anthropic"
        self.model = ""
        self.base_url = ""
        self.api_key = ""
        for p in ("anthropic", "openrouter", "openai", "deepseek", "gemini"):
            setattr(self, f"{p}_api_key", "")
        for k, v in kw.items():
            setattr(self, k, v)


# These tests construct a real OpenAI-compatible client and need the openai SDK
# (installed in the venv, not in the bare test env).
def _openai_missing():
    try:
        import openai  # noqa: F401
        return False
    except ImportError:
        return True


sdk = pytest.mark.skipif(_openai_missing(), reason="openai SDK not installed")


def test_unknown_provider_rejected():
    # Provider check happens before any SDK import — runs everywhere.
    with pytest.raises(ProviderError):
        build_client(Cfg(provider="hal9000", api_key="x"))


@sdk
def test_openrouter_uses_correct_base_url():
    c = build_client(Cfg(provider="openrouter", openrouter_api_key="k"))
    # OpenAICompatibleClient stores the client; assert base_url wired through.
    assert c._client.base_url is not None
    assert "openrouter.ai" in str(c._client.base_url)


@sdk
def test_default_model_per_provider():
    c = build_client(Cfg(provider="deepseek", deepseek_api_key="k"))
    assert c._model == PROVIDER_DEFAULT_MODELS["deepseek"]


@sdk
def test_explicit_model_overrides_default():
    c = build_client(Cfg(provider="openrouter", openrouter_api_key="k",
                         model="google/gemini-2.0-flash"))
    assert c._model == "google/gemini-2.0-flash"


@sdk
def test_generic_api_key_fallback():
    # No provider-specific key, but generic api_key set — should work.
    c = build_client(Cfg(provider="gemini", api_key="generic"))
    assert "generativelanguage" in str(c._client.base_url)


def test_missing_key_raises():
    with pytest.raises(ProviderError):
        build_client(Cfg(provider="openai"))


def test_summarizer_is_provider_agnostic():
    class FakeClient:
        def complete(self, system, user):
            return '[{"point": "Grace abounds", "scripture": "Romans 5:20"}]'
    s = Summarizer(FakeClient())
    points = s.summarize("some sermon text")
    assert len(points) == 1
    assert points[0].scripture == "Romans 5:20"


def test_summarizer_never_crashes_on_provider_error():
    class Boom:
        def complete(self, system, user):
            raise RuntimeError("provider 503")
    s = Summarizer(Boom())
    assert s.summarize("text") == []  # keeps last slide, no raise


def test_all_providers_have_default_model():
    for provider in ("anthropic",) + tuple(PROVIDER_BASE_URLS):
        assert provider in PROVIDER_DEFAULT_MODELS
