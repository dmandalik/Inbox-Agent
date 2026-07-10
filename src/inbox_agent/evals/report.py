"""Render an :class:`EvalResult` as text tables, a confusion matrix, or Markdown."""

from __future__ import annotations

from inbox_agent.evals.harness import EvalResult


def render_text(result: EvalResult) -> str:
    """A per-class precision/recall/F1 table plus aggregate lines."""
    lines = []
    lines.append(f"Triage eval — backend: {result.backend}, n={result.n}")
    lines.append("")
    header = f"{'category':<16}{'prec':>7}{'recall':>8}{'f1':>7}{'support':>9}"
    lines.append(header)
    lines.append("-" * len(header))
    for label in result.labels:
        m = result.per_class[label]
        lines.append(f"{label:<16}{m.precision:>7.2f}{m.recall:>8.2f}{m.f1:>7.2f}{m.support:>9}")
    lines.append("-" * len(header))
    lines.append(
        f"{'macro avg':<16}{result.macro_precision:>7.2f}"
        f"{result.macro_recall:>8.2f}{result.macro_f1:>7.2f}{result.n:>9}"
    )
    lines.append(f"{'accuracy':<16}{result.accuracy:>7.2f}")
    return "\n".join(lines)


def render_confusion(result: EvalResult) -> str:
    """A text confusion matrix (rows = true, cols = predicted)."""
    labels = result.labels
    abbrev = [label[:4] for label in labels]
    width = max(6, *(len(a) for a in abbrev))
    head = " " * 16 + "".join(f"{a:>{width}}" for a in abbrev)
    lines = ["Confusion matrix (rows=true, cols=pred):", head]
    for label in labels:
        row = result.confusion[label]
        cells = "".join(f"{row[p]:>{width}}" for p in labels)
        lines.append(f"{label:<16}{cells}")
    return "\n".join(lines)


def render_markdown(result: EvalResult) -> str:
    """A Markdown per-class F1 table (for pasting into the README)."""
    lines = [
        f"**Backend:** `{result.backend}` · **n:** {result.n} · "
        f"**accuracy:** {result.accuracy:.2f} · **macro-F1:** {result.macro_f1:.2f}",
        "",
        "| category | precision | recall | F1 | support |",
        "|----------|----------:|-------:|---:|--------:|",
    ]
    for label in result.labels:
        m = result.per_class[label]
        lines.append(f"| {label} | {m.precision:.2f} | {m.recall:.2f} | {m.f1:.2f} | {m.support} |")
    lines.append(
        f"| **macro avg** | {result.macro_precision:.2f} | "
        f"{result.macro_recall:.2f} | {result.macro_f1:.2f} | {result.n} |"
    )
    return "\n".join(lines)
