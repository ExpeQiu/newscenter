"use client";

import Link from "next/link";
import { useTransition } from "react";
import type { Item } from "@/lib/api";
import { api } from "@/lib/api";

export function ItemCard({
  item,
  reason,
  onChange,
}: {
  item: Item;
  reason?: string;
  onChange?: (item: Item) => void;
}) {
  const [pending, start] = useTransition();
  const summary = item.summary || item.body?.slice(0, 120) || "摘要生成中…";

  function toggle(field: "is_read" | "is_starred") {
    start(async () => {
      const next = await api.patchMarks(item.id, {
        [field]: !item.marks[field],
      });
      onChange?.(next);
    });
  }

  return (
    <article
      className={`group border-b border-[var(--line)] py-5 transition-opacity duration-300 ${
        item.marks.is_read ? "opacity-55" : "opacity-100"
      } ${pending ? "opacity-70" : ""}`}
    >
      <div className="mb-1 flex items-center gap-2 text-xs text-[var(--muted)]">
        <span className="uppercase tracking-wide">{item.source_type}</span>
        {item.ai_category ? <span>· {item.ai_category}</span> : null}
        {item.embed_provider ? <span>· 视频</span> : null}
      </div>
      <Link href={`/items/${item.id}`} className="block">
        <h2 className="font-[family-name:var(--font-display)] text-xl leading-snug text-[var(--ink)] group-hover:text-[var(--accent)] transition-colors">
          {item.title || "无标题"}
        </h2>
        <p className="mt-2 text-[15px] leading-relaxed text-[var(--body)] line-clamp-2">{summary}</p>
        {reason ? <p className="mt-2 text-xs text-[var(--accent)]">{reason}</p> : null}
      </Link>
      <div className="mt-3 flex gap-3 text-sm">
        <button type="button" onClick={() => toggle("is_read")} className="text-[var(--muted)] hover:text-[var(--ink)]">
          {item.marks.is_read ? "标未读" : "已读"}
        </button>
        <button type="button" onClick={() => toggle("is_starred")} className="text-[var(--muted)] hover:text-[var(--ink)]">
          {item.marks.is_starred ? "取消星标" : "星标"}
        </button>
        <Link href={`/items/${item.id}`} className="text-[var(--accent)]">
          打开
        </Link>
      </div>
    </article>
  );
}
