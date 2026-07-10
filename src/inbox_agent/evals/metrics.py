"""Classification metrics, stdlib-only.

All functions take aligned ``y_true``/``y_pred`` label lists plus the fixed set
of ``labels`` (so classes with zero support still appear). Precision/recall/F1
follow the standard one-vs-rest definitions; division-by-zero yields 0.0.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassMetrics:
    """Per-class scores."""

    label: str
    support: int  # number of true instances of this class
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def confusion_matrix(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> dict[str, dict[str, int]]:
    """Return ``matrix[true][pred] = count`` over the given label set."""
    matrix = {t: dict.fromkeys(labels, 0) for t in labels}
    for yt, yp in zip(y_true, y_pred, strict=True):
        if yt in matrix and yp in matrix[yt]:
            matrix[yt][yp] += 1
    return matrix


def precision_recall_f1(
    y_true: list[str], y_pred: list[str], labels: list[str]
) -> dict[str, ClassMetrics]:
    """Per-class precision/recall/F1 (one-vs-rest)."""
    out: dict[str, ClassMetrics] = {}
    for label in labels:
        tp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt == label and yp == label)
        fp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt != label and yp == label)
        fn = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt == label and yp != label)
        support = sum(1 for yt in y_true if yt == label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        out[label] = ClassMetrics(
            label=label,
            support=support,
            tp=tp,
            fp=fp,
            fn=fn,
            precision=precision,
            recall=recall,
            f1=f1,
        )
    return out


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    """Fraction of exactly-correct predictions."""
    if not y_true:
        return 0.0
    correct = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if yt == yp)
    return correct / len(y_true)


def macro_average(per_class: dict[str, ClassMetrics]) -> tuple[float, float, float]:
    """Unweighted mean of (precision, recall, F1) across classes."""
    if not per_class:
        return 0.0, 0.0, 0.0
    n = len(per_class)
    p = sum(m.precision for m in per_class.values()) / n
    r = sum(m.recall for m in per_class.values()) / n
    f = sum(m.f1 for m in per_class.values()) / n
    return p, r, f
