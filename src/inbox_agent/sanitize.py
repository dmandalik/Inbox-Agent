"""HTML sanitization for displaying real email bodies.

Emails are UNTRUSTED. We keep the original HTML so the reader can show real
formatting, but it is **never** rendered raw — every body passes through
:func:`sanitize_html` first. We use ``nh3`` (the Rust ``ammonia`` sanitizer),
which drops ``<script>``, event handlers (``onclick`` …), ``javascript:`` URLs,
``<iframe>``/``<object>``/``<form>``, and anything not on the allowlist below,
while keeping the tags and inline styles emails rely on for layout.

Remaining caveat (a privacy one, not an XSS one): permitted ``<img>`` tags can
load remote images, which senders use as read-tracking pixels. That is a
deliberate product trade-off to preserve formatting; a "block remote images"
toggle is a natural future addition.
"""

from __future__ import annotations

import nh3

# Tags emails use for text, lists, tables, and layout. Everything else is dropped.
_ALLOWED_TAGS = {
    "a",
    "b",
    "i",
    "u",
    "em",
    "strong",
    "p",
    "br",
    "hr",
    "span",
    "div",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "td",
    "th",
    "img",
    "center",
    "small",
    "sub",
    "sup",
    "s",
    "strike",
    "del",
    "ins",
    "caption",
    "colgroup",
    "col",
}

# `style`/`class`/dimensions carry most of an email's formatting; safe to show.
_COMMON = {
    "style",
    "class",
    "align",
    "valign",
    "width",
    "height",
    "bgcolor",
    "color",
    "dir",
    "title",
}
_ALLOWED_ATTRS: dict[str, set[str]] = {
    "*": _COMMON,
    "a": _COMMON | {"href", "target", "name"},  # `rel` is managed by link_rel
    "img": _COMMON | {"src", "alt", "srcset"},
    "font": _COMMON | {"face", "size"},
    "td": _COMMON | {"colspan", "rowspan"},
    "th": _COMMON | {"colspan", "rowspan"},
    "table": _COMMON | {"cellpadding", "cellspacing", "border"},
    "col": _COMMON | {"span"},
    "colgroup": _COMMON | {"span"},
}


def sanitize_html(html: str) -> str:
    """Return a safe-to-render version of ``html`` (empty string for empty input)."""
    if not html or not html.strip():
        return ""
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        link_rel="noopener noreferrer nofollow",
    )
