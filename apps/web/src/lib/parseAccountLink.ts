/** 从主页 / 空间链接识别平台与账号标识，便于订阅页粘贴绑定。 */

export type SocialPlatform = "weibo" | "x" | "xiaohongshu" | "other";
export type VideoPlatform = "bilibili" | "youtube";

export type ParsedSocialLink = {
  kind: "social";
  platform: SocialPlatform;
  handle: string;
  suggestedName: string;
};

export type ParsedVideoLink = {
  kind: "video";
  type: VideoPlatform;
  account: string;
  suggestedName: string;
};

export type ParsedAccountLink = ParsedSocialLink | ParsedVideoLink;

const X_RESERVED = new Set([
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
]);

function tryUrl(raw: string): URL | null {
  const t = raw.trim();
  if (!t) return null;
  try {
    if (/^https?:\/\//i.test(t)) return new URL(t);
    if (/^(www\.|m\.|space\.|x\.com|twitter\.com|weibo\.|xiaohongshu\.|xhslink\.|youtube\.|youtu\.be|bilibili\.)/i.test(t)) {
      return new URL(`https://${t}`);
    }
  } catch {
    return null;
  }
  return null;
}

function hostOf(u: URL): string {
  return u.hostname.replace(/^www\./i, "").toLowerCase();
}

function decodePathSeg(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

/** 是否像可识别的主页链接（含无协议的常见域名）。 */
export function looksLikeAccountUrl(raw: string): boolean {
  const t = raw.trim();
  if (!t) return false;
  if (/^https?:\/\//i.test(t)) return true;
  return /(?:weibo\.|x\.com|twitter\.com|xiaohongshu\.|xhslink\.|bilibili\.|youtube\.|youtu\.be|space\.bilibili)/i.test(
    t
  );
}

export function parseSocialLink(raw: string): ParsedSocialLink | null {
  const u = tryUrl(raw);
  if (!u) return null;
  const host = hostOf(u);
  const parts = u.pathname.split("/").filter(Boolean).map(decodePathSeg);

  // 微博
  if (host === "weibo.com" || host === "m.weibo.cn" || host.endsWith(".weibo.com")) {
    // /u/123 /n/昵称 /profile/123
    if (parts[0] === "u" && parts[1] && /^\d{5,16}$/.test(parts[1])) {
      return social("weibo", parts[1], parts[1]);
    }
    if (parts[0] === "n" && parts[1]) {
      return social("weibo", parts[1], parts[1]);
    }
    if (parts[0] === "profile" && parts[1] && /^\d{5,16}$/.test(parts[1])) {
      return social("weibo", parts[1], parts[1]);
    }
    // m.weibo.cn/u/123
    if (host === "m.weibo.cn" && parts[0] === "u" && parts[1]) {
      return social("weibo", parts[1], parts[1]);
    }
    // weibo.com/1234567890
    if (parts[0] && /^\d{5,16}$/.test(parts[0]) && !["p", "ttarticle", "tv"].includes(parts[0])) {
      return social("weibo", parts[0], parts[0]);
    }
    return null;
  }

  // X / Twitter
  if (host === "x.com" || host === "twitter.com" || host === "mobile.twitter.com") {
    const seg = parts[0]?.replace(/^@/, "") || "";
    if (!seg || X_RESERVED.has(seg.toLowerCase())) return null;
    if (!/^[A-Za-z0-9_]{1,15}$/.test(seg)) return null;
    return social("x", seg, `@${seg}`);
  }

  // 小红书
  if (
    host === "xiaohongshu.com" ||
    host.endsWith(".xiaohongshu.com") ||
    host === "xhslink.com" ||
    host.endsWith(".xhslink.com")
  ) {
    // /user/profile/{id}
    const profileIdx = parts.indexOf("profile");
    if (parts[0] === "user" && profileIdx === 1 && parts[2]) {
      const id = parts[2].split("?")[0];
      if (id) return social("xiaohongshu", id, id.slice(0, 12));
    }
    // 短链无法在前端解出用户 id
    if (host.includes("xhslink")) return null;
    return null;
  }

  return null;
}

export function parseVideoLink(raw: string): ParsedVideoLink | null {
  const u = tryUrl(raw);
  if (!u) return null;
  const host = hostOf(u);
  const parts = u.pathname.split("/").filter(Boolean).map(decodePathSeg);

  // B 站
  if (host === "bilibili.com" || host.endsWith(".bilibili.com") || host === "b23.tv") {
    // space.bilibili.com/{mid}
    if (host === "space.bilibili.com" && parts[0] && /^\d{1,16}$/.test(parts[0])) {
      return video("bilibili", parts[0], `B站 ${parts[0]}`);
    }
    // m.bilibili.com/space/{mid} 或 bilibili.com/space/{mid}
    const spaceIdx = parts.indexOf("space");
    if (spaceIdx >= 0 && parts[spaceIdx + 1] && /^\d{1,16}$/.test(parts[spaceIdx + 1])) {
      const mid = parts[spaceIdx + 1];
      return video("bilibili", mid, `B站 ${mid}`);
    }
    // 任意 bilibili URL 中的 /12345678/
    const midHit = u.pathname.match(/\/(\d{5,16})(?:\/|$|\?)/);
    if (host.startsWith("space.") && midHit) {
      return video("bilibili", midHit[1], `B站 ${midHit[1]}`);
    }
    return null;
  }

  // YouTube
  if (
    host === "youtube.com" ||
    host === "m.youtube.com" ||
    host === "music.youtube.com" ||
    host === "youtu.be"
  ) {
    // /channel/UCxxxx
    const chIdx = parts.indexOf("channel");
    if (chIdx >= 0 && parts[chIdx + 1] && /^UC[\w-]{22}$/.test(parts[chIdx + 1])) {
      const id = parts[chIdx + 1];
      return video("youtube", id, id);
    }
    // /@handle
    const at = parts.find((p) => p.startsWith("@"));
    if (at) {
      const handle = at.slice(1);
      if (handle) return video("youtube", `@${handle}`, `@${handle}`);
    }
    // /c/name /user/name
    if ((parts[0] === "c" || parts[0] === "user") && parts[1]) {
      return video("youtube", parts[1], parts[1]);
    }
    return null;
  }

  return null;
}

/** 按上下文解析；未指定 kind 时先试视频再试社媒。 */
export function parseAccountLink(
  raw: string,
  prefer?: "social" | "video"
): ParsedAccountLink | null {
  const t = raw.trim();
  if (!t || !looksLikeAccountUrl(t)) return null;
  if (prefer === "social") return parseSocialLink(t);
  if (prefer === "video") return parseVideoLink(t);
  return parseVideoLink(t) || parseSocialLink(t);
}

function social(platform: SocialPlatform, handle: string, suggestedName: string): ParsedSocialLink {
  return { kind: "social", platform, handle, suggestedName };
}

function video(type: VideoPlatform, account: string, suggestedName: string): ParsedVideoLink {
  return { kind: "video", type, account, suggestedName };
}

export function socialParseHint(p: ParsedSocialLink): string {
  const labels: Record<SocialPlatform, string> = {
    weibo: "微博",
    x: "X / Twitter",
    xiaohongshu: "小红书",
    other: "其他",
  };
  return `${labels[p.platform]} · ${p.handle}`;
}

export function videoParseHint(p: ParsedVideoLink): string {
  return `${p.type === "bilibili" ? "B 站" : "YouTube"} · ${p.account}`;
}
