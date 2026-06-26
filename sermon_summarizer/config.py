"""Runtime configuration, loaded from config.json or environment.

API key resolution order: config.json `anthropic_api_key` -> ANTHROPIC_API_KEY
env var. The example file (config.example.json) ships with placeholders; the
real config.json is gitignored.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # Provider: anthropic | openrouter | openai | deepseek | gemini
    provider: str = "anthropic"
    model: str = ""  # blank = provider default (see providers.PROVIDER_DEFAULT_MODELS)
    base_url: str = ""  # blank = provider default; override for self-hosted/proxy

    # API keys. Use the one matching `provider`, or the generic `api_key`.
    api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    audio_device_index: int | None = None
    whisper_model_size: str = "small"
    whisper_cpu_threads: int = 2
    summarize_interval_seconds: int = 300
    transcript_window_seconds: int = 300
    max_points_per_slide: int = 6
    second_screen_index: int = 1  # 0 = primary, 1 = the TV
    church_name: str = ""

    # Display appearance (changeable live from the control panel, persisted).
    theme: str = "Midnight"
    font_scale: float = 1.0
    background_image: str = ""
    logo_image: str = ""

    _path: str = "config.json"  # remembered for save()

    @classmethod
    def load(cls, path: str | os.PathLike = "config.json") -> "Config":
        data: dict = {}
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text())
        cfg = cls(**{k: v for k, v in data.items()
                     if k in cls.__dataclass_fields__ and k != "_path"})
        cfg._path = str(path)
        # Env-var fallbacks per provider, only when the config field is blank.
        env_map = {
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "gemini_api_key": "GEMINI_API_KEY",
        }
        for field_name, env_name in env_map.items():
            if not getattr(cfg, field_name):
                setattr(cfg, field_name, os.environ.get(env_name, ""))
        return cfg

    def save(self, path: str | os.PathLike | None = None) -> None:
        """Persist all fields back to config.json so display/provider choices
        survive a restart. Merges into the existing file to preserve formatting
        of unknown keys."""
        target = Path(path or self._path)
        existing: dict = {}
        if target.exists():
            try:
                existing = json.loads(target.read_text())
            except (json.JSONDecodeError, ValueError):
                existing = {}
        for k in self.__dataclass_fields__:
            if k == "_path":
                continue
            existing[k] = getattr(self, k)
        target.write_text(json.dumps(existing, indent=2) + "\n")

    def has_key_for_provider(self) -> bool:
        """True if a usable key exists for the configured provider."""
        provider = (self.provider or "anthropic").lower()
        specific = getattr(self, f"{provider}_api_key", "") or ""
        return bool(specific or self.api_key)
