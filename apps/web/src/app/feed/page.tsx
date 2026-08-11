"use client";

import { useEffect, useState } from "react";
import { api, type Item } from "@/lib/api";
import { ItemCard } from "@/components/ItemCard";

const CHANNELS = [
  { v: "", l: "全部渠道" },
  { v: "rss", l: "RSS" },
  { v: "youtube", l: "YouTube" },
  { v: "bilibili", l: "B站" },
];

const CONTENT_TYPES = [
  { v: "", l: "全部类型" },
  { v: "news", l: "新闻" },
  { v: "image", l: "图片" },
  { v: "video", l: "视频" },
];

export default function FeedPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [source, setSource] = useState("");
  const [contentType, setContentType] = useState("");
  const [unread, setUnread] = useState(false);

  async function load(s = source, ct = contentType, u = unread) {
    const q = new URLSearchParams();
    if (s) q.set("source_type", s);
    if (ct) q.set("content_type", ct);
    if (u) q.set("unread", "true");
    q.set("limit", "40");
    const data = await api.items(`?${q.toString()}`);
    setItems(data.items);
  }

  useEffect(() => {
    load().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="animate-fade-up">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">浏览</h1>

      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-1.5 text-xs uppercase tracking-wide text-[var(--muted)]">渠道</div>
          <div className="flex flex-wrap gap-2 text-sm">
            {CHANNELS.map((o) => (
              <button
                key={o.v || "ch-all"}
                type="button"
                onClick={() => {
                  setSource(o.v);
                  load(o.v, contentType, unread);
                }}
                className={`rounded-md px-3 py-1.5 ${
                  source === o.v
                    ? "bg-[var(--ink)] text-[var(--bg)]"
                    : "bg-[var(--surface)] text-[var(--body)]"
                }`}
              >
                {o.l}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-1.5 text-xs uppercase tracking-wide text-[var(--muted)]">内容类型</div>
          <div className="flex flex-wrap gap-2 text-sm">
            {CONTENT_TYPES.map((o) => (
              <button
                key={o.v || "ct-all"}
                type="button"
                onClick={() => {
                  setContentType(o.v);
                  load(source, o.v, unread);
                }}
                className={`rounded-md px-3 py-1.5 ${
                  contentType === o.v
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--surface)] text-[var(--body)]"
                }`}
              >
                {o.l}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                const next = !unread;
                setUnread(next);
                load(source, contentType, next);
              }}
              className={`rounded-md px-3 py-1.5 ${
                unread ? "bg-[var(--ink)] text-[var(--bg)]" : "bg-[var(--surface)] text-[var(--body)]"
              }`}
            >
              仅未读
            </button>
          </div>
        </div>
      </div>

      <div className="mt-2">
        {items.map((item) => (
          <ItemCard
            key={item.id}
            item={item}
            onChange={(next) => setItems((prev) => prev.map((x) => (x.id === next.id ? next : x)))}
          />
        ))}
        {items.length === 0 ? <p className="mt-8 text-sm text-[var(--muted)]">暂无内容。</p> : null}
      </div>
    </div>
  );
}
