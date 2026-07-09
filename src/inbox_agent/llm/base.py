"""The ``LLMClient`` interface.

Deliberately minimal: a single ``complete(system, user)`` call returning text.
Keeping it small means the model-cascade router and local/fine-tuned models
(later phases) implement one method. Embeddings live behind a *separate*
interface (Phase 2) so the two never entangle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """A text-in/text-out chat completion client."""

    #: The model id this client targets (for logs/telemetry).
    model: str = "unknown"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        """Return the assistant's text reply for a system + user prompt."""
        raise NotImplementedError
