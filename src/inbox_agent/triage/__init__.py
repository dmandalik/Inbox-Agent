"""Triage: classify emails into a fixed category set.

The :class:`~inbox_agent.triage.base.Classifier` interface and its backends
(``stub``, ``llm``) are added alongside the LLM client. For now this package
exposes the canonical taxonomy, which the synthetic generator and the eval
harness both rely on.
"""

from inbox_agent.triage.categories import (
    CATEGORIES,
    CATEGORY_DESCRIPTIONS,
    DEFAULT_CATEGORY,
    is_valid_category,
)

__all__ = [
    "CATEGORIES",
    "CATEGORY_DESCRIPTIONS",
    "DEFAULT_CATEGORY",
    "is_valid_category",
]
