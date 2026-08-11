"""X / social collectors — metadata only (no media download)."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from pipeline.normalize import CollectItem

logger = logging.getLogger("newsc.social_cli.collector")

# Public web client bearer (same as x.com guest); override via NEWSC_X_BEARER.
_DEFAULT_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
# GraphQL operation ids rotate; override via env when Twitter bumps them.
_DEFAULT_QID_USER = "sLVLhk0bGj3MVFEKTdax1w"
_DEFAULT_QID_TWEETS = "E3opETHurmVJflFsUBVuUQ"

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEMO = [
    {
        "handle": "Google",
        "tweet_id": "20",
        "text": "Demo X post — NewsC social collector stub for offline verify.",
    }
]


def resolve_handle(account: str) -> str:
    acc = (account or "").strip()
    if not acc:
        raise ValueError("empty x handle")
    m = re.search(r"(?:x\.com|twitter\.com)/@?([A-Za-z0-9_]{1,15})", acc, re.I)
    if m:
        return m.group(1)
    handle = acc.lstrip("@")
    if not _HANDLE_RE.match(handle):
        raise ValueError(f"invalid x handle: {account!r}")
    return handle


def collect_demo() -> list[CollectItem]:
    now = datetime.now(timezone.utc)
    items: list[CollectItem] = []
    for d in DEMO:
        handle = d["handle"]
        tid = d["tweet_id"]
        items.append(
            CollectItem(
                source="social",
                title=f"@{handle}: {d['text'][:80]}",
                content=d["text"],
                url=f"https://x.com/{handle}/status/{tid}",
                published_at=now,
                content_type="news",
                raw={"demo": True, "platform": "x", "handle": handle, "tweet_id": tid},
            )
        )
    return items


def _tweet_features() -> dict[str, bool]:
    return {
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }


def _user_features() -> dict[str, bool]:
    return {
        "hidden_profile_subscriptions_enabled": True,
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "subscriptions_verification_info_is_identity_verified_enabled": True,
        "subscriptions_verification_info_verified_since_enabled": True,
        "highlights_tweets_tab_ui_enabled": True,
        "responsive_web_twitter_article_notes_tab_enabled": True,
        "subscriptions_feature_can_gift_premium": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    }


def _legacy_from_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet") or {}
    return result.get("legacy") or {}


def _parse_created(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except Exception:  # noqa: BLE001
        return None


def _media_thumb(legacy: dict[str, Any]) -> str | None:
    media = ((legacy.get("entities") or {}).get("media")) or []
    if not media:
        media = ((legacy.get("extended_entities") or {}).get("media")) or []
    if not media:
        return None
    url = media[0].get("media_url_https") or media[0].get("media_url")
    return str(url) if url else None


def collect_x_user(
    handle: str,
    *,
    source_label: str = "",
    limit: int = 20,
    timeout: float = 40.0,
) -> list[CollectItem]:
    """Fetch recent posts via X guest GraphQL (UserByScreenName + UserTweets)."""
    screen = resolve_handle(handle)
    bearer = os.getenv("NEWSC_X_BEARER", _DEFAULT_BEARER)
    qid_user = os.getenv("NEWSC_X_QID_USER", _DEFAULT_QID_USER)
    qid_tweets = os.getenv("NEWSC_X_QID_TWEETS", _DEFAULT_QID_TWEETS)
    logger.info("x_collect start handle=%s limit=%s", screen, limit)

    headers = {
        "User-Agent": _UA,
        "Authorization": f"Bearer {bearer}",
        "Accept": "*/*",
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
    }
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        guest_resp = client.post("https://api.twitter.com/1.1/guest/activate.json")
        guest_resp.raise_for_status()
        guest = (guest_resp.json() or {}).get("guest_token")
        if not guest:
            raise RuntimeError("x guest_token missing")
        client.headers["x-guest-token"] = str(guest)

        user_resp = client.get(
            f"https://twitter.com/i/api/graphql/{qid_user}/UserByScreenName",
            params={
                "variables": json.dumps(
                    {"screen_name": screen, "withSafetyModeUserFields": True}
                ),
                "features": json.dumps(_user_features()),
            },
        )
        user_resp.raise_for_status()
        user_json = user_resp.json()
        user_result = ((user_json.get("data") or {}).get("user") or {}).get("result") or {}
        rest_id = str(user_result.get("rest_id") or "").strip()
        display = (
            ((user_result.get("legacy") or {}).get("name"))
            or source_label
            or screen
        )
        if not rest_id:
            raise RuntimeError(
                f"x user not found @{screen} (check NEWSC_X_QID_USER if query rotated)"
            )

        tweets_resp = client.get(
            f"https://twitter.com/i/api/graphql/{qid_tweets}/UserTweets",
            params={
                "variables": json.dumps(
                    {
                        "userId": rest_id,
                        "count": min(max(limit, 1), 40),
                        "includePromotedContent": False,
                        "withQuickPromoteEligibilityTweetFields": True,
                        "withVoice": True,
                        "withV2Timeline": True,
                    }
                ),
                "features": json.dumps(_tweet_features()),
            },
        )
        tweets_resp.raise_for_status()
        payload = tweets_resp.json()

    timeline = (
        (((payload.get("data") or {}).get("user") or {}).get("result") or {})
        .get("timeline_v2", {})
        .get("timeline", {})
    )
    instructions = timeline.get("instructions") or []
    entries: list[dict[str, Any]] = []
    for ins in instructions:
        if ins.get("type") == "TimelineAddEntries":
            entries = ins.get("entries") or []
            break

    items: list[CollectItem] = []
    for entry in entries:
        content = entry.get("content") or {}
        item_content = content.get("itemContent") or {}
        result = ((item_content.get("tweet_results") or {}).get("result")) or {}
        legacy = _legacy_from_result(result)
        text = (legacy.get("full_text") or "").strip()
        tid = str(legacy.get("id_str") or "").strip()
        if not text or not tid:
            continue
        user_screen = (
            ((legacy.get("user_id_str") and screen) or screen)
        )
        # Prefer author screen from core user results when present
        core_user = (
            ((result.get("core") or {}).get("user_results") or {}).get("result") or {}
        )
        core_legacy = core_user.get("legacy") or {}
        if core_legacy.get("screen_name"):
            user_screen = str(core_legacy["screen_name"])
        url = f"https://x.com/{user_screen}/status/{tid}"
        title_body = re.sub(r"\s+", " ", text)[:100]
        items.append(
            CollectItem(
                source="social",
                title=f"@{user_screen}: {title_body}",
                content=text,
                url=url,
                published_at=_parse_created(legacy.get("created_at")),
                thumbnail_url=_media_thumb(legacy),
                content_type="news",
                raw={
                    "platform": "x",
                    "handle": screen,
                    "display_name": display,
                    "tweet_id": tid,
                    "rest_id": rest_id,
                    "is_quote_status": legacy.get("is_quote_status"),
                    "retweeted": text.startswith("RT @"),
                },
            )
        )
        if len(items) >= limit:
            break

    logger.info(
        "x_collect done handle=%s display=%s items=%s",
        screen,
        display,
        len(items),
    )
    if not items:
        raise RuntimeError(
            f"x timeline empty for @{screen} (check NEWSC_X_QID_TWEETS if query rotated)"
        )
    return items


def collect_by_social(
    *,
    platform: str,
    handle: str,
    source_label: str = "",
    limit: int = 20,
) -> list[CollectItem]:
    """Dispatch social platforms; currently X only."""
    plat = (platform or "other").strip().lower()
    if plat in ("x", "twitter"):
        return collect_x_user(handle, source_label=source_label, limit=limit)
    logger.info("social_skip unsupported platform=%s handle=%s", plat, handle)
    return []
