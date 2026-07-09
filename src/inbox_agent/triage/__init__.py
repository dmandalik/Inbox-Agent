"""Triage: classify emails into a fixed category set.

One :class:`~inbox_agent.triage.base.Classifier` interface with two backends —
a keyless deterministic :class:`~inbox_agent.triage.stub.StubClassifier` and a
zero-shot :class:`~inbox_agent.triage.llm.LLMClassifier`. Select via
``TRIAGE_BACKEND`` (see :func:`build_classifier`).
"""

from inbox_agent.triage.base import Classifier
from inbox_agent.triage.categories import (
    CATEGORIES,
    CATEGORY_DESCRIPTIONS,
    DEFAULT_CATEGORY,
    is_valid_category,
)
from inbox_agent.triage.factory import build_classifier

__all__ = [
    "CATEGORIES",
    "CATEGORY_DESCRIPTIONS",
    "DEFAULT_CATEGORY",
    "Classifier",
    "build_classifier",
    "is_valid_category",
]
