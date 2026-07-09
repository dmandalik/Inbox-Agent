"""Select a triage :class:`Classifier` from settings.

``TRIAGE_BACKEND=stub`` needs nothing (keyless, offline). ``llm`` builds an
LLM client and fails loudly if the key/URL/model are missing.
"""

from __future__ import annotations

from inbox_agent.config import Settings, get_settings
from inbox_agent.triage.base import Classifier


def build_classifier(settings: Settings | None = None) -> Classifier:
    """Return the classifier named by ``TRIAGE_BACKEND`` ("llm" | "stub")."""
    settings = settings or get_settings()
    backend = settings.triage_backend

    if backend == "stub":
        from inbox_agent.triage.stub import StubClassifier

        return StubClassifier()

    if backend == "llm":
        # require_llm() raises a clear ConfigError if unconfigured.
        from inbox_agent.llm import build_llm_client
        from inbox_agent.triage.llm import LLMClassifier

        return LLMClassifier(build_llm_client(settings))

    raise ValueError(f"unknown TRIAGE_BACKEND: {backend!r} (expected 'llm' or 'stub')")
