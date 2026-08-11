"""从主页 / 空间链接解析平台与账号标识。"""
from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlparse

logger = logging.getLogger("newsc.account_link")

_X_RESERVED = frozenset(
    {
        "home",
        "explore",
        "search",
        "settings",
        "i",
        "intent",
        "share",
        "compose",
        "messages",
        "notifications",
        "login",
        "signup",
        "tos",
        "privacy",
    }
)


def _ensure_url(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    if re.match(r"^https?://", t, re.I):
        return t
    if re.match(
        r"^(www\.|m\.|space\.|x\.com|twitter\.com|weibo\.|xiaohongshu\.|"
        r"xhslink\.|youtube\.|youtu\.be|bilibili\.)",
        t,
        re.I,
    ):
        return f"https://{t}"
    return None


def _host(netloc: str) -> str:
    h = (netloc or "").split("@")[-1].lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def _parts(path: str) -> list[str]:
    return [unquote(p) for p in (path or "").split("/") if p]


def looks_like_account_url(raw: str) -> bool:
    t = (raw or "").strip()
    if not t:
        return False
    if re.match(r"^https?://", t, re.I):
        return True
    return bool(
        re.search(
            r"(?:weibo\.|x\.com|twitter\.com|xiaohongshu\.|xhslink\.|"
            r"bilibili\.|youtube\.|youtu\.be|space\.bilibili)",
            t,
            re.I,
        )
    )


def parse_social_link(raw: str) -> dict[str, str] | None:
    url = _ensure_url(raw)
    if not url:
        return None
    try:
        u = urlparse(url)
    except ValueError:
        return None
    host = _host(u.netloc)
    parts = _parts(u.path)

    if host in ("weibo.com", "m.weibo.cn") or host.endswith(".weibo.com"):
        if len(parts) >= 2 and parts[0] == "u" and re.fullmatch(r"\d{5,16}", parts[1]):
            return _social("weibo", parts[1], parts[1])
        if len(parts) >= 2 and parts[0] == "n" and parts[1]:
            return _social("weibo", parts[1], parts[1])
        if len(parts) >= 2 and parts[0] == "profile" and re.fullmatch(r"\d{5,16}", parts[1]):
            return _social("weibo", parts[1], parts[1])
        if parts and re.fullmatch(r"\d{5,16}", parts[0]) and parts[0] not in ("p",):
            return _social("weibo", parts[0], parts[0])
        return None

    if host in ("x.com", "twitter.com", "mobile.twitter.com"):
        seg = (parts[0] if parts else "").lstrip("@")
        if not seg or seg.lower() in _X_RESERVED:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", seg):
            return None
        return _social("x", seg, f"@{seg}")

    if (
        host == "xiaohongshu.com"
        or host.endswith(".xiaohongshu.com")
        or host == "xhslink.com"
        or host.endswith(".xhslink.com")
    ):
        if len(parts) >= 3 and parts[0] == "user" and parts[1] == "profile" and parts[2]:
            uid = parts[2].split("?")[0]
            if uid:
                return _social("xiaohongshu", uid, uid[:12])
        return None

    return None


def parse_video_link(raw: str) -> dict[str, str] | None:
    url = _ensure_url(raw)
    if not url:
        return None
    try:
        u = urlparse(url)
    except ValueError:
        return None
    host = _host(u.netloc)
    parts = _parts(u.path)

    if host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv":
        if host == "space.bilibili.com" and parts and re.fullmatch(r"\d{1,16}", parts[0]):
            mid = parts[0]
            return _video("bilibili", mid, f"B站 {mid}")
        if "space" in parts:
            i = parts.index("space")
            if i + 1 < len(parts) and re.fullmatch(r"\d{1,16}", parts[i + 1]):
                mid = parts[i + 1]
                return _video("bilibili", mid, f"B站 {mid}")
        return None

    if host in ("youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"):
        if "channel" in parts:
            i = parts.index("channel")
            if i + 1 < len(parts) and re.fullmatch(r"UC[\w-]{22}", parts[i + 1]):
                cid = parts[i + 1]
                return _video("youtube", cid, cid)
        for p in parts:
            if p.startswith("@") and len(p) > 1:
                handle = p[1:]
                return _video("youtube", f"@{handle}", f"@{handle}")
        if len(parts) >= 2 and parts[0] in ("c", "user") and parts[1]:
            return _video("youtube", parts[1], parts[1])
        return None

    return None


def canonicalize_social(platform: str, handle: str) -> tuple[str, str]:
    """若 handle 为链接则解析；返回 (platform, handle)。"""
    h = (handle or "").strip()
    plat = (platform or "other").strip().lower() or "other"
    if looks_like_account_url(h):
        parsed = parse_social_link(h)
        if parsed:
            logger.info(
                "account_link_social_ok platform=%s handle=%s from=%s",
                parsed["platform"],
                parsed["handle"],
                h[:120],
            )
            return parsed["platform"], parsed["handle"]
        logger.warning("account_link_social_fail raw=%s", h[:120])
    return plat, h.lstrip("@")


def canonicalize_video(stype: str, account: str) -> str:
    """若 account 为链接且与 stype 匹配，则规范化为账号标识。"""
    acc = (account or "").strip()
    t = (stype or "").strip().lower()
    if looks_like_account_url(acc):
        parsed = parse_video_link(acc)
        if parsed:
            if parsed["type"] == t:
                logger.info(
                    "account_link_video_ok type=%s account=%s from=%s",
                    parsed["type"],
                    parsed["account"],
                    acc[:120],
                )
                return parsed["account"]
            logger.warning(
                "account_link_video_type_mismatch expect=%s got=%s raw=%s",
                t,
                parsed["type"],
                acc[:120],
            )
        else:
            logger.warning("account_link_video_fail raw=%s", acc[:120])
    return acc


def _social(platform: str, handle: str, suggested_name: str) -> dict[str, str]:
    return {
        "kind": "social",
        "platform": platform,
        "handle": handle,
        "suggested_name": suggested_name,
    }


def _video(vtype: str, account: str, suggested_name: str) -> dict[str, str]:
    return {
        "kind": "video",
        "type": vtype,
        "account": account,
        "suggested_name": suggested_name,
    }
