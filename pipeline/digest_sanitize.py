"""Lightweight HTML sanitization for trusted local agent digests."""
from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_JS_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR_UNQUOTED_RE = re.compile(r"\s+on[a-z]+\s*=\s*[^\s>]+", re.IGNORECASE)
_JS_HREF_RE = re.compile(r"""\s+(href|src)\s*=\s*(['"])\s*javascript:[^'"]*\2""", re.IGNORECASE)
_IFRAME_RE = re.compile(r"<iframe\b[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL)
_OBJECT_RE = re.compile(r"<(object|embed|link|meta)\b[^>]*/?>", re.IGNORECASE)


def sanitize_digest_html(html: str) -> str:
    """Strip script/event handlers; keep structural markup for local digests."""
    if not html:
        return ""
    out = _SCRIPT_RE.sub("", html)
    out = _STYLE_JS_RE.sub("", out)  # avoid CSS expression / @import abuse in digests
    out = _IFRAME_RE.sub("", out)
    out = _OBJECT_RE.sub("", out)
    out = _EVENT_ATTR_RE.sub("", out)
    out = _EVENT_ATTR_UNQUOTED_RE.sub("", out)
    out = _JS_HREF_RE.sub("", out)
    return out.strip()
