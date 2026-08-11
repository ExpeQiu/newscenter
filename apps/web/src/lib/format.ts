/** 相对时间 / 短日期，用于列表发布信息。 */
export function formatPublishedAt(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) {
    return d.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
  }
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  if (days < 365) {
    return d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
  }
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
}

/** 观看/评论等计数：1234 → 1234；12345 → 1.2万 */
export function formatCount(value?: number | string | null): string | null {
  if (value == null || value === "" || value === "--") return null;
  const n = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(n) || n < 0) return null;
  if (n >= 100_000_000) {
    const s = (n / 100_000_000).toFixed(1).replace(/\.0$/, "");
    return `${s}亿`;
  }
  if (n >= 10_000) {
    const s = (n / 10_000).toFixed(1).replace(/\.0$/, "");
    return `${s}万`;
  }
  return String(Math.floor(n));
}
