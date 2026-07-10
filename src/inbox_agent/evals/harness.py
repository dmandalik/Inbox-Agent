"""Eval runner: align predictions with ground truth and compute an EvalResult."""

from __future__ import annotations

from dataclasses import dataclass

from inbox_agent.evals.metrics import (
    ClassMetrics,
    accuracy,
    confusion_matrix,
    macro_average,
    precision_recall_f1,
)
from inbox_agent.triage.categories import CATEGORIES


@dataclass(frozen=True)
class EvalResult:
    """A complete evaluation over a set of (true, predicted) label pairs."""

    labels: list[str]
    n: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, ClassMetrics]
    confusion: dict[str, dict[str, int]]
    backend: str = "unknown"


def evaluate(
    ground_truth: dict[str, str],
    predictions: dict[str, str],
    *,
    labels: list[str] | None = None,
    backend: str = "unknown",
) -> EvalResult:
    """Score ``predictions`` against ``ground_truth`` (both message_id -> label).

    Only message_ids present in *both* maps are scored. Raises if the overlap is
    empty (nothing to evaluate — usually means triage hasn't been run).
    """
    labels = list(labels) if labels is not None else list(CATEGORIES)
    ids = sorted(set(ground_truth) & set(predictions))
    if not ids:
        raise ValueError(
            "No overlapping message_ids between predictions and ground truth. "
            "Did you run `inbox-agent triage` after `ingest`?"
        )
    y_true = [ground_truth[i] for i in ids]
    y_pred = [predictions[i] for i in ids]

    per_class = precision_recall_f1(y_true, y_pred, labels)
    macro_p, macro_r, macro_f = macro_average(per_class)
    return EvalResult(
        labels=labels,
        n=len(ids),
        accuracy=accuracy(y_true, y_pred),
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f,
        per_class=per_class,
        confusion=confusion_matrix(y_true, y_pred, labels),
        backend=backend,
    )
