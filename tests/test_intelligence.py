from intelligence.factory import create_provider
from intelligence.contracts import SummarizeIn, ItemRef
from pipeline.normalize import CollectItem, content_hash


def test_mock_provider_name():
    assert create_provider().name == "mock"


def test_content_hash_stable():
    a = CollectItem(source="rss", title="Hello", content="World", url="https://x.test/1")
    b = CollectItem(source="rss", title="Hello", content="World", url="https://x.test/1")
    assert content_hash(a) == content_hash(b)


def test_summarize_contract():
    p = create_provider()
    out = p.summarize(SummarizeIn(item=ItemRef(id="1", title="标题", body="正文内容")))
    assert "标题" in out.summary
