"""Deterministic keyword/sender-rule classifier — the keyless backend.

No key, no network: this is what CI and smoke tests run, and it guarantees the
full pipeline works offline. Rules are ordered by precedence and tuned to the
taxonomy; they are intentionally simple (the ``llm`` backend is what generalizes
to real, unseen mail).
"""

from __future__ import annotations

from inbox_agent.models import Email
from inbox_agent.triage.base import Classifier
from inbox_agent.triage.categories import DEFAULT_CATEGORY

# Markers that strongly indicate scams / phishing / prompt-injection payloads.
_SPAM_MARKERS = (
    "ignore all previous instructions",
    "disregard your",
    "system override",
    "you have won",
    "claim your prize",
    "verify your identity",
    "account will be suspended",
    "bank details",
    "onboarding fee",
    "customs fee",
    "$400/day",
    "no experience",
)
_RECEIPT_MARKERS = (
    "your order",
    "order confirmed",
    "is confirmed",
    "has shipped",
    "receipt",
    "invoice",
    "total: $",
    "tracking:",
    "estimated delivery",
)
_NEWSLETTER_MARKERS = (
    "unsubscribe",
    "you subscribed",
    "subscription preferences",
    "manage your subscription",
    "digest",
    "weekend edition",
    "issue #",
    "this week in",
)
_NOTIFICATION_MARKERS = (
    "reminder:",
    "do not reply",
    "automated",
    "new sign-in",
    "new episode",
    "activity summary",
    "ci passed",
    "event updated",
    "no action is needed",
    "no action required",
)
_WORK_MARKERS = (
    "postmortem",
    "planning",
    "roadmap",
    "agenda",
    "review by",
    "pto request",
    "client demo",
    "vendor renewal",
    "liability clause",
)

_NOTIFICATION_LOCALPARTS = ("no-reply", "noreply", "notifications", "alerts")
_RECEIPT_LOCALPARTS = ("orders", "receipts")
_PERSONAL_DOMAINS = ("example.org", "example.net")
_WORK_DOMAIN = "northwind.example.com"
_SPAM_DOMAIN_SUFFIX = ".example.biz"


def _localpart(addr: str) -> str:
    return addr.split("@", 1)[0].lower()


def _domain(addr: str) -> str:
    return addr.split("@", 1)[-1].lower()


class StubClassifier(Classifier):
    """Rule-based, deterministic classifier (no key, no network)."""

    name = "stub"

    def classify(self, email: Email) -> str:
        text = f"{email.subject}\n{email.body}".lower()
        domain = _domain(email.from_addr)
        local = _localpart(email.from_addr)

        # 1. Spam / phishing (incl. injection payloads) — highest priority.
        if domain.endswith(_SPAM_DOMAIN_SUFFIX) or _any(text, _SPAM_MARKERS):
            return "spam_phishing"

        # 2. Receipts / orders.
        if local in _RECEIPT_LOCALPARTS or _any(text, _RECEIPT_MARKERS):
            return "receipt_order"

        # 3. Newsletters.
        if _any(text, _NEWSLETTER_MARKERS):
            return "newsletter"

        # 4. Automated notifications (by sender or phrasing).
        if local in _NOTIFICATION_LOCALPARTS or _any(text, _NOTIFICATION_MARKERS):
            return "notification"

        # 5. Work — by known corporate domain first (high precision)…
        if domain == _WORK_DOMAIN:
            return "work"

        # 6. Personal — friends' personal domains.
        if domain in _PERSONAL_DOMAINS:
            return "personal"

        # 7. …then work by content markers.
        if _any(text, _WORK_MARKERS):
            return "work"

        return DEFAULT_CATEGORY


def _any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)
