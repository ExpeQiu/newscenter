"""RSS since cursor filtering (no network)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from rss_cli import collector


def test_collect_feed_since_filters(monkeypatch):
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class FakeFeed:
        entries = [
            SimpleNamespace(
                title="old",
                link="https://x/old",
                published="Tue, 01 Jan 2024 00:00:00 +0000",
                summary="o",
                id="1",
            ),
            SimpleNamespace(
                title="new",
                link="https://x/new",
                published="Thu, 01 Jan 2026 00:00:00 +0000",
                summary="n",
                id="2",
            ),
        ]

    monkeypatch.setattr(collector.feedparser, "parse", lambda url: FakeFeed())
    items = collector.collect_feed("https://example/rss", since=old.isoformat())
    assert len(items) == 1
    assert items[0].title == "new"
    assert items[0].published_at is not None
    # sanity: new timestamp retained
    assert items[0].published_at.year == new.year


SAMPLE_ZAOPAN = """
<html><body>
<div class="banner-bg"><div id="block_2123">金句内容足够长用于测试 ——作者</div></div>
<div class="content">
  <div class="yestoday"><dl><dt>昨日收盘指数</dt><dd>上证指数： 100</dd></dl></div>
  <div class="content-main clearfix">
    <div class="content-main-fl fl">
      <div id="block_2125"><p>【昨日国内行情回顾】正文段落一。更多分析内容写在这里以便超过长度阈值。</p>
      <p>第二段正文继续描述市场情况与板块轮动。</p></div>
    </div>
    <div class="content-main-fr fr">
      <div>侧栏推荐</div><div>停牌</div><div>大宗交易</div><div>广告位</div>
    </div>
  </div>
</div>
<div class="foot">免责声明：测试页脚 Copyright Foo 软件下载 回顶部</div>
</body></html>
"""


def test_strip_removes_sidebar_and_footer():
    main = collector._extract_main_html(SAMPLE_ZAOPAN)
    text = collector._strip_to_text(main)
    assert "行情回顾" in text
    assert "金句内容" in text or "昨日收盘" in text
    assert "免责声明" not in text
    assert "大宗交易" not in text
    assert "回顶部" not in text


def test_trim_boilerplate_text():
    raw = "正文开始。" + ("市场分析与板块解读。" * 30) + "\n免责声明：仅供参考\n软件下载\n"
    out = collector._trim_boilerplate_text(raw)
    assert "正文开始" in out
    assert "免责声明" not in out
    assert len(out) > 200
