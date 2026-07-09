"""LLM access behind a thin, provider-agnostic interface.

``LLMClient`` is the seam; ``OpenAICompatibleClient`` is the one implementation,
driven entirely by env vars so Groq / Gemini / OpenRouter / Ollama / LM Studio
are a ``.env`` change, not a code change.
"""

from inbox_agent.llm.base import LLMClient
from inbox_agent.llm.factory import build_llm_client
from inbox_agent.llm.openai_client import OpenAICompatibleClient

__all__ = ["LLMClient", "OpenAICompatibleClient", "build_llm_client"]
