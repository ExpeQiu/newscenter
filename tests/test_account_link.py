"""account_link 解析用例。"""
from __future__ import annotations

from orchestrator.account_link import (
    canonicalize_social,
    canonicalize_video,
    parse_social_link,
    parse_video_link,
)


def test_parse_social_x_and_weibo():
    assert parse_social_link("https://x.com/elonmusk")["handle"] == "elonmusk"
    assert parse_social_link("https://weibo.com/u/1234567890")["platform"] == "weibo"
    xhs = parse_social_link(
        "https://www.xiaohongshu.com/user/profile/5f3a1b2c3d4e5f6a7b8c9d0e?xsec_token=1"
    )
    assert xhs and xhs["handle"] == "5f3a1b2c3d4e5f6a7b8c9d0e"


def test_parse_video_bilibili_youtube():
    assert parse_video_link("https://space.bilibili.com/2")["account"] == "2"
    assert parse_video_link("https://www.youtube.com/@Google")["account"] == "@Google"
    yt = parse_video_link("https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw")
    assert yt and yt["account"].startswith("UC")


def test_canonicalize():
    plat, handle = canonicalize_social("weibo", "https://x.com/foo")
    assert plat == "x" and handle == "foo"
    assert canonicalize_video("bilibili", "https://space.bilibili.com/99") == "99"
    # 平台不匹配时不改写
    assert canonicalize_video("youtube", "https://space.bilibili.com/99") == (
        "https://space.bilibili.com/99"
    )
