"""Settings, read from the environment (optionally via a git-ignored ``.env``).

Two rules this file exists to enforce:

1. No secret is ever hardcoded or given a real default.
2. Missing required config **fails loudly** with an actionable message rather
   than falling back to a value that would silently produce garbage.

Gmail credentials and the LLM key are kept separate on purpose: Gmail is never
required (the synthetic source is the default), and the LLM key is needed only
for ``TRIAGE_BACKEND=llm``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Required configuration is missing or inconsistent."""


class LLMSettings(NamedTuple):
    """Validated, non-optional LLM settings (from :meth:`Settings.require_llm`)."""

    base_url: str
    api_key: str
    model: str


class Settings(BaseSettings):
    """Environment-driven settings. Get one via :func:`get_settings`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # LLM (OpenAI-compatible). Optional at load time; validated on use.
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    triage_backend: Literal["llm", "stub"] = "llm"

    # Gmail: optional, read-only, never required.
    gmail_credentials_path: Path = Path("var/credentials.json")
    gmail_token_path: Path = Path("var/token.json")
    gmail_scope: str = "https://www.googleapis.com/auth/gmail.readonly"

    # SQLite lives under git-ignored var/ so it can never be committed.
    db_path: Path = Path("var/inbox.db")

    def require_llm(self) -> LLMSettings:
        """Return validated LLM settings, or raise a clear :class:`ConfigError`.

        Only the ``llm`` code path calls this, so the stub backend never needs
        a key.
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
                f"The LLM is not configured. Missing: {', '.join(missing)}.\n"
                "Set these in .env:\n"
                "  a free key from Groq (https://console.groq.com) or Google AI\n"
                "  Studio (https://aistudio.google.com/apikey), or a local Ollama.\n"
                "For triage only, you can skip the LLM with TRIAGE_BACKEND=stub.\n"
                "See .env.example for provider presets."
            )
        return LLMSettings(self.llm_base_url, self.llm_api_key, self.llm_model)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` (reads the environment once)."""
    return Settings()
