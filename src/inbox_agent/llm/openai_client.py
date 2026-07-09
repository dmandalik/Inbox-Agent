"""OpenAI-compatible LLM client.

Talks the OpenAI chat-completions protocol, so the same class works against any
compatible endpoint (Groq, Gemini's OpenAI-compat URL, OpenRouter, local
Ollama/LM Studio). Adds explicit 429/5xx/timeout backoff on top of the SDK.
"""

from __future__ import annotations

from inbox_agent.llm.base import LLMClient
from inbox_agent.llm.retry import with_retries
from inbox_agent.obs import get_logger
from inbox_agent.obs.redact import redact_secret

_log = get_logger("llm.openai")


def _is_retryable(exc: Exception) -> bool:
    """True for transient OpenAI-protocol errors worth retrying."""
    # Imported lazily so this module imports even if openai isn't resolved yet.
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    if isinstance(
        exc,
        (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError),
    ):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or 500 <= exc.status_code < 600
    return False


class OpenAICompatibleClient(LLMClient):
    """Chat client over any OpenAI-compatible endpoint, with backoff."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_retries: int = 5,
        timeout: float = 30.0,
    ) -> None:
        from openai import OpenAI

        # SDK-level retries are disabled; we own the backoff loop for clarity
        # and testability (see llm/retry.py).
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)
        self.model = model
        self.base_url = base_url
        self._max_retries = max_retries
        _log.info(
            "llm client ready model=%s base_url=%s api_key=%s",
            model,
            base_url,
            redact_secret(api_key),
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        def _call() -> str:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (resp.choices[0].message.content or "").strip()

        return with_retries(_call, is_retryable=_is_retryable, max_retries=self._max_retries)
