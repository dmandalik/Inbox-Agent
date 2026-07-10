"""Scoring triage predictions against ground-truth labels.

Metrics are hand-rolled stdlib — precision/recall/F1 are ~10 lines each, and
seeing them written out is more useful here than a scikit-learn dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from inbox_agent.triage import CATEGORIES


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


@dataclass(frozen=True)
class ClassMetrics:
    """One-vs-rest scores for a single category."""

    support: int  # how many emails truly belong to this class
    precision: float  # of those we predicted, how many were right
    recall: float  # of those that truly are, how many we found
    f1: float  # harmonic mean of the two


@dataclass(frozen=True)
class EvalResult:
    """A complete evaluation over aligned (true, predicted) label pairs."""

    labels: list[str]
    n: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, ClassMetrics]
    confusion: dict[str, dict[str, int]]  # confusion[true][predicted] = count
    backend: str


def evaluate(
    ground_truth: dict[str, str],
    predictions: dict[str, str],
    *,
    labels: list[str] | None = None,
    backend: str = "unknown",
) -> EvalResult:
    """Score ``predictions`` against ``ground_truth`` (both message_id -> label).

    Only message_ids present in *both* maps are scored, so a partial triage run
    still evaluates cleanly. Raises if there is no overlap at all.
    """
    labels = list(labels) if labels is not None else list(CATEGORIES)
    ids = sorted(set(ground_truth) & set(predictions))
    if not ids:
        raise ValueError(
            "No overlapping message_ids between predictions and ground truth. "
            "Did you run `inbox-agent triage` after `ingest`?"
        )
    pairs = [(ground_truth[i], predictions[i]) for i in ids]

    per_class: dict[str, ClassMetrics] = {}
    for label in labels:
        tp = sum(1 for t, p in pairs if t == label and p == label)
        fp = sum(1 for t, p in pairs if t != label and p == label)
        fn = sum(1 for t, p in pairs if t == label and p != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_class[label] = ClassMetrics(
            support=tp + fn,
            precision=precision,
            recall=recall,
            f1=_safe_div(2 * precision * recall, precision + recall),
        )

    confusion = {t: dict.fromkeys(labels, 0) for t in labels}
    for true, pred in pairs:
        if true in confusion and pred in confusion[true]:
            confusion[true][pred] += 1

    n_labels = len(per_class) or 1
    return EvalResult(
        labels=labels,
        n=len(pairs),
        accuracy=_safe_div(sum(1 for t, p in pairs if t == p), len(pairs)),
        macro_precision=sum(m.precision for m in per_class.values()) / n_labels,
        macro_recall=sum(m.recall for m in per_class.values()) / n_labels,
        macro_f1=sum(m.f1 for m in per_class.values()) / n_labels,
        per_class=per_class,
        confusion=confusion,
        backend=backend,
    )


def render_text(result: EvalResult) -> str:
    """A per-class precision/recall/F1 table with aggregates."""
    header = f"{'category':<16}{'prec':>7}{'recall':>8}{'f1':>7}{'support':>9}"
    rule = "-" * len(header)
    rows = [
        f"{label:<16}{m.precision:>7.2f}{m.recall:>8.2f}{m.f1:>7.2f}{m.support:>9}"
        for label, m in ((label, result.per_class[label]) for label in result.labels)
    ]
    return "\n".join(
        [
            f"Triage eval — backend: {result.backend}, n={result.n}",
            "",
            header,
            rule,
            *rows,
            rule,
            f"{'macro avg':<16}{result.macro_precision:>7.2f}"
            f"{result.macro_recall:>8.2f}{result.macro_f1:>7.2f}{result.n:>9}",
            f"{'accuracy':<16}{result.accuracy:>7.2f}",
        ]
    )


def render_confusion(result: EvalResult) -> str:
    """A text confusion matrix (rows = true, cols = predicted)."""
    width = 6
    head = " " * 16 + "".join(f"{label[:4]:>{width}}" for label in result.labels)
    rows = [
        f"{label:<16}" + "".join(f"{result.confusion[label][p]:>{width}}" for p in result.labels)
        for label in result.labels
    ]
    return "\n".join(["Confusion matrix (rows=true, cols=pred):", head, *rows])


def render_markdown(result: EvalResult) -> str:
    """A Markdown table, for pasting into the README."""
    rows = [
        f"| {label} | {m.precision:.2f} | {m.recall:.2f} | {m.f1:.2f} | {m.support} |"
        for label, m in ((label, result.per_class[label]) for label in result.labels)
    ]
    return "\n".join(
        [
            f"**Backend:** `{result.backend}` · **n:** {result.n} · "
            f"**accuracy:** {result.accuracy:.2f} · **macro-F1:** {result.macro_f1:.2f}",
            "",
            "| category | precision | recall | F1 | support |",
            "|----------|----------:|-------:|---:|--------:|",
            *rows,
            f"| **macro avg** | {result.macro_precision:.2f} | "
            f"{result.macro_recall:.2f} | {result.macro_f1:.2f} | {result.n} |",
        ]
    )
