"""Evaluation harness: score triage predictions against ground-truth labels.

Metrics are hand-rolled in stdlib (no scikit-learn) — a small, transparent
computation: per-class precision/recall/F1, macro/micro aggregates, accuracy,
and a confusion matrix.
"""

from inbox_agent.evals.harness import EvalResult, evaluate
from inbox_agent.evals.metrics import ClassMetrics, confusion_matrix, precision_recall_f1
from inbox_agent.evals.report import render_confusion, render_markdown, render_text

__all__ = [
    "ClassMetrics",
    "EvalResult",
    "confusion_matrix",
    "evaluate",
    "precision_recall_f1",
    "render_confusion",
    "render_markdown",
    "render_text",
]
