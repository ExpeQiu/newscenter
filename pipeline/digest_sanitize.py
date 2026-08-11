"""Lightweight HTML sanitization for trusted local agent digests."""
from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR_UNQUOTED_RE = re.compile(r"\s+on[a-z]+\s*=\s*[^\s>]+", re.IGNORECASE)
_JS_HREF_RE = re.compile(r"""\s+(href|src)\s*=\s*(['"])\s*javascript:[^'"]*\2""", re.IGNORECASE)
_IFRAME_RE = re.compile(r"<iframe\b[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL)
_OBJECT_RE = re.compile(r"<(object|embed)\b[^>]*/?>", re.IGNORECASE)
# 注入页面时去掉外链资源；iframe 文档预览保留 charset/viewport meta 与 style
_LINK_META_RE = re.compile(r"<(link|meta)\b[^>]*/?>", re.IGNORECASE)


def _strip_active(html: str) -> str:
    out = _SCRIPT_RE.sub("", html)
    out = _IFRAME_RE.sub("", out)
    out = _OBJECT_RE.sub("", out)
    out = _EVENT_ATTR_RE.sub("", out)
    out = _EVENT_ATTR_UNQUOTED_RE.sub("", out)
    out = _JS_HREF_RE.sub("", out)
    return out


def sanitize_digest_html(html: str) -> str:
    """嵌入宿主页时用：去 script/style/事件，避免污染主站样式。"""
    if not html:
        return ""
    out = _strip_active(html)
    out = _STYLE_RE.sub("", out)
    out = _LINK_META_RE.sub("", out)
    return out.strip()


def sanitize_digest_html_document(html: str) -> str:
    """完整 HTML 文档预览（iframe）：保留 style/meta，仅去脚本与事件。"""
    if not html:
        return ""
    return _strip_active(html).strip()
