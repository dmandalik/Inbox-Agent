"""Structured inbox tools — the no-LLM layer (design doc, L0 / Track B).

Some questions don't need a language model at all: "how many unread?", "how many
from Priya?", "star everything from the newsletter". Answering those by reading
SQL and applying a filter is instant, free, and exact — so the chat engine tries
this path first and only falls back to retrieval + LLM for open questions.

Two pieces:

* :func:`parse_intent` — a deterministic, keyword-based parser that turns a
  message into a :class:`Intent` (count / action / question) plus a
  :class:`Filter`. No model, so it is predictable and fully testable. Anything it
  can't confidently classify becomes a ``question`` and flows to normal chat.
* the tools themselves — :func:`select`, :func:`count`, :func:`apply_action` —
  pure functions over the repository.

Actions (star / archive / mark read) write only local app state, never the Gmail
account, and are reversible; the caller reports exactly what changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from inbox_agent.models import Email
from inbox_agent.security import detect_injection
from inbox_agent.store import EmailRepository
from inbox_agent.triage import StubClassifier

# Words a user might use for each category, mapped to the canonical id.
_CATEGORY_WORDS: dict[str, str] = {
    "work": "work",
    "personal": "personal",
    "newsletter": "newsletter",
    "newsletters": "newsletter",
    "receipt": "receipt_order",
    "receipts": "receipt_order",
    "order": "receipt_order",
    "orders": "receipt_order",
    "notification": "notification",
    "notifications": "notification",
    "spam": "spam_phishing",
    "phishing": "spam_phishing",
}

# Words that mean "looks like a manipulation/injection attempt" (the flagged set).
_FLAGGED_WORDS = ("flagged", "suspicious", "manipulation", "injection", "scam")

_ACTIONS = {
    "star": "star",
    "flag": "star",
    "unstar": "unstar",
    "unflag": "unstar",
    "archive": "archive",
}


@dataclass
class Filter:
    """A normalized inbox filter. All conditions are ANDed."""

    category: str | None = None
    sender: str | None = None
    unread: bool = False
    starred: bool = False
    flagged: bool = False

    def is_empty(self) -> bool:
        return not (self.category or self.sender or self.unread or self.starred or self.flagged)

    def describe(self) -> str:
        """Human phrasing like 'unread work emails from priya'."""
        bits = []
        if self.unread:
            bits.append("unread")
        if self.starred:
            bits.append("starred")
        if self.flagged:
            bits.append("suspicious")
        if self.category:
            bits.append(self.category.replace("_", "/"))
        noun = " ".join([*bits, "emails"]) if bits else "emails"
        return f"{noun} from {self.sender}" if self.sender else noun


@dataclass
class Intent:
    """What the user asked for, structurally."""

    kind: str  # "count" | "action" | "label" | "reply" | "question"
    filter: Filter = field(default_factory=Filter)
    action: str | None = None  # set when kind == "action" (star/unstar/archive/read/unread)
    value: str | None = None  # label name (kind == "label") or reply text (kind == "reply")


_COUNT_RE = re.compile(r"\b(how many|number of|count( of)?|how much)\b", re.I)


def _parse_filter(message: str) -> Filter:
    """Pull category / sender / state conditions out of a message."""
    low = message.lower()
    f = Filter()
    for word, cat in _CATEGORY_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            f.category = cat
            break
    if "unread" in low:
        f.unread = True
    if "starred" in low or "flagged as important" in low:
        f.starred = True
    if any(w in low for w in _FLAGGED_WORDS):
        f.flagged = True
    # "from <name>": take the tail after the last 'from', trimmed of filler.
    m = re.search(r"\bfrom\s+(.+)$", low)
    if m:
        sender = m.group(1).strip(" ?.!\"'")
        sender = re.sub(r"^(the|my)\s+", "", sender)
        # Drop trailing noise like "from priya about the invoice".
        sender = re.split(r"\b(about|regarding|re|that|who|which|with|as)\b", sender)[0].strip()
        if sender:
            f.sender = sender
    return f


def parse_intent(message: str) -> Intent:
    """Classify a message into a structured intent. Unsure ⇒ ``question``.

    Most-specific patterns first (reply/label/mark) before the plain
    star/archive verbs, so "mark ... as read" isn't mistaken for a star.
    """
    low = message.lower().strip()

    # Reply: "reply to Priya saying I'll review Friday", "respond to the vendor: ok"
    m = re.match(r"^\s*(?:reply|respond)(?:\s+to)?\s+(.+)$", low)
    if m:
        parts = re.split(r"\b(?:saying|that|with)\b\s*|:\s*", m.group(1), maxsplit=1)
        target = parts[0].strip(" ,")
        body = message[len(message) - len(parts[1]) :].strip() if len(parts) > 1 else ""
        filt = _parse_filter(f"from {target}")
        if filt.sender:
            return Intent("reply", filt, value=body)

    # Label: "label all from Priya as Work", "tag newsletters as Reading"
    m = re.match(r"^\s*(?:label|tag)\s+(.*?)\s+as\s+(.+)$", low)
    if m:
        filt = _parse_filter(m.group(1))
        name = message[message.lower().rfind(" as ") + 4 :].strip()  # keep original case
        if not filt.is_empty() and name:
            return Intent("label", filt, value=name)

    # Mark read / unread: "mark all from X as read", "mark newsletters unread"
    if re.match(r"^\s*mark\b", low):
        action = "unread" if "unread" in low else ("read" if "read" in low else None)
        if action:
            # strip the read/unread words so they aren't parsed as filters
            filt = _parse_filter(re.sub(r"\b(un)?read\b", " ", low))
            if not filt.is_empty():
                return Intent("action", filt, action)

    # Star / unstar / archive.
    for verb, action in _ACTIONS.items():
        if re.search(rf"^\s*(please\s+)?{verb}\b", low):
            filt = _parse_filter(low)
            # Require a real target so a bare "star" doesn't nuke the inbox.
            if not filt.is_empty():
                return Intent("action", filt, action)

    # Count: "how many ...", "number of ...".
    if _COUNT_RE.search(low):
        return Intent("count", _parse_filter(low))

    return Intent("question")


def _resolve_category(email: Email, preds: dict[str, str], stub: StubClassifier) -> str:
    return preds.get(email.message_id) or stub.classify(email)


def select(repo: EmailRepository, filt: Filter, *, include_archived: bool = False) -> list[Email]:
    """Emails matching ``filt`` (archived excluded unless asked), newest first."""
    emails = repo.all()
    states = repo.states()
    preds = repo.predictions()
    stub = StubClassifier()
    out = []
    for e in emails:
        st = states.get(e.message_id, {})
        if not include_archived and st.get("archived"):
            continue
        if filt.category and _resolve_category(e, preds, stub) != filt.category:
            continue
        if filt.sender and filt.sender not in f"{e.from_name} {e.from_addr}".lower():
            continue
        if filt.unread and st.get("read"):
            continue
        if filt.starred and not st.get("starred"):
            continue
        if filt.flagged and not detect_injection(f"{e.subject}\n{e.body}"):
            continue
        out.append(e)
    return out


def count(repo: EmailRepository, filt: Filter) -> int:
    return len(select(repo, filt))


def apply_action(repo: EmailRepository, emails: list[Email], action: str) -> list[str]:
    """Apply a state action to each email. Returns the affected message ids."""
    patch = {
        "star": {"starred": True},
        "unstar": {"starred": False},
        "archive": {"archived": True},
        "read": {"read": True},
        "unread": {"read": False},
    }[action]
    ids = []
    for e in emails:
        repo.set_state(e.message_id, **patch)
        ids.append(e.message_id)
    return ids
