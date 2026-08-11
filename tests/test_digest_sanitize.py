from pipeline.digest_sanitize import sanitize_digest_html


def test_strips_script_and_handlers():
    raw = '<p onclick="alert(1)">hi</p><script>evil()</script><a href="javascript:x">x</a>'
    out = sanitize_digest_html(raw)
    assert "<script" not in out.lower()
    assert "onclick" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "hi" in out
