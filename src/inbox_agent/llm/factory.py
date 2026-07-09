"""Build an :class:`LLMClient` from validated settings.

Fails loudly (via ``Settings.require_llm``) if the LLM env vars are missing, so
the ``llm`` triage backend never silently produces garbage.
"""

from __future__ import annotations

from inbox_agent.config import Settings, get_settings
from inbox_agent.llm.base import LLMClient
from inbox_agent.llm.openai_client import OpenAICompatibleClient


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Return a configured OpenAI-compatible client (raises if unconfigured)."""
    settings = settings or get_settings()
    llm = settings.require_llm()  # ConfigError if BASE_URL/MODEL/API_KEY missing
    return OpenAICompatibleClient(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.model,
    )
