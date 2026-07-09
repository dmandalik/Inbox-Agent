"""Application configuration.

All settings come from the environment (optionally via a git-ignored ``.env``).
Hard rules enforced here:

* No secret is ever hardcoded or given a real default.
* Two credential kinds are kept separate: a **Gmail** credential (never required;
  the synthetic source is the default) and an **LLM key** (needed only for the
  ``llm`` triage backend, and only a free/card-free one is expected).
* Validation fails *loudly* with an actionable message rather than falling back
  to a bogus value that would silently produce garbage.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TriageBackend = Literal["llm", "stub"]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or inconsistent."""


class LLMSettings:
    """Validated, non-optional LLM settings (produced by ``Settings.require_llm``)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model


class Settings(BaseSettings):
    """Environment-driven settings. Instantiate via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM (OpenAI-compatible); optional at load time, validated on use -----
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    # --- Triage -------------------------------------------------------------
    triage_backend: TriageBackend = "llm"

    # --- Embeddings (Phase 2) -----------------------------------------------
    embedding_backend: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Gmail (optional, read-only, never required) ------------------------
    gmail_credentials_path: Path = Path("var/credentials.json")
    gmail_token_path: Path = Path("var/token.json")
    gmail_scope: str = "https://www.googleapis.com/auth/gmail.readonly"

    # --- Storage ------------------------------------------------------------
    db_path: Path = Field(default=Path("var/inbox.db"))

    def require_llm(self) -> LLMSettings:
        """Return validated LLM settings or raise a clear :class:`ConfigError`.

        Called only on the ``llm`` code path, so the stub backend never needs a
        key. Keeps the "fail loudly, no hardcoded fallback" guarantee.
        """
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", self.llm_base_url),
                ("LLM_MODEL", self.llm_model),
                ("LLM_API_KEY", self.llm_api_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Triage backend 'llm' needs "
                + ", ".join(missing)
                + " but "
                + ("it is" if len(missing) == 1 else "they are")
                + " unset.\n"
                "Fix one of:\n"
                "  1. Put a FREE key in .env (Groq: https://console.groq.com , "
                "or Google AI Studio: https://aistudio.google.com/apikey), or\n"
                "  2. Run keyless: set TRIAGE_BACKEND=stub (no key, no network).\n"
                "See .env.example for provider presets."
            )
        assert self.llm_base_url and self.llm_api_key and self.llm_model  # for type-checkers
        return LLMSettings(self.llm_base_url, self.llm_api_key, self.llm_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance (reads env once)."""
    return Settings()
