"""The canonical triage taxonomy — single source of truth.

Both the synthetic generator and every classifier import this list, so labels
can never drift apart. Six mutually-exclusive categories chosen to cover the
common shape of a personal/work inbox while staying small enough to get clean
per-class F1 on a modest corpus.
"""

from __future__ import annotations

# Ordering here is also the display/confusion-matrix order.
CATEGORIES: tuple[str, ...] = (
    "newsletter",  # bulk editorial / digests / marketing you subscribed to
    "work",  # colleague/business threads needing attention or reply
    "receipt_order",  # purchase receipts, order/shipping confirmations
    "personal",  # notes from friends & family
    "spam_phishing",  # unsolicited scams, fraud, credential phishing
    "notification",  # automated app/system alerts (no human reply expected)
)

# Fallback used when a classifier cannot produce a valid label.
DEFAULT_CATEGORY = "notification"

# Human-readable hints; used to build the zero-shot prompt and to document intent.
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "newsletter": "Bulk editorial content or marketing digests the user subscribed to.",
    "work": "Business or colleague correspondence that expects the user's attention or reply.",
    "receipt_order": "Purchase receipts, order confirmations, invoices, or shipping updates.",
    "personal": "Personal messages from friends or family.",
    "spam_phishing": "Unsolicited scams, fraud, or attempts to steal credentials or money.",
    "notification": "Automated system or app notifications that need no human reply.",
}


def is_valid_category(label: str) -> bool:
    """True if ``label`` is one of the canonical categories."""
    return label in CATEGORIES
