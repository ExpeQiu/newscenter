from pipeline.digest_sanitize import sanitize_digest_html, sanitize_digest_html_document


def test_strips_script_and_handlers():
    raw = '<p onclick="alert(1)">hi</p><script>evil()</script><a href="javascript:x">x</a>'
    out = sanitize_digest_html(raw)
    assert "<script" not in out.lower()
    assert "onclick" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "hi" in out


def test_document_keeps_style():
    raw = "<!DOCTYPE html><html><head><style>h1{color:red}</style></head><body><h1>T</h1><script>x()</script></body></html>"
    out = sanitize_digest_html_document(raw)
    assert "<style" in out.lower()
    assert "color:red" in out
    assert "<script" not in out.lower()
    embed = sanitize_digest_html(raw)
    assert "<style" not in embed.lower()
