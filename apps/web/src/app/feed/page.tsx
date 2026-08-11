"use client";

import { useEffect, useState } from "react";
import { api, type Item } from "@/lib/api";
import { ItemCard } from "@/components/ItemCard";

export default function FeedPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [source, setSource] = useState("");
  const [unread, setUnread] = useState(false);

  async function load(s = source, u = unread) {
    const q = new URLSearchParams();
    if (s) q.set("source_type", s);
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
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        {[
          { v: "", l: "全部" },
          { v: "rss", l: "RSS" },
          { v: "youtube", l: "YouTube" },
          { v: "bilibili", l: "B站" },
        ].map((o) => (
          <button
            key={o.v || "all"}
            type="button"
            onClick={() => {
              setSource(o.v);
              load(o.v, unread);
            }}
            className={`rounded-md px-3 py-1.5 ${
              source === o.v ? "bg-[var(--ink)] text-[var(--bg)]" : "bg-[var(--surface)] text-[var(--body)]"
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
            load(source, next);
          }}
          className={`rounded-md px-3 py-1.5 ${
            unread ? "bg-[var(--accent)] text-white" : "bg-[var(--surface)] text-[var(--body)]"
          }`}
        >
          仅未读
        </button>
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
