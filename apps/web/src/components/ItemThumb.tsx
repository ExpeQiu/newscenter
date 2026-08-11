"use client";

import Link from "next/link";
import { useTransition } from "react";
import type { Item } from "@/lib/api";
import { api } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  news: "新闻",
  image: "图片",
  video: "视频",
};

function coverSrc(item: Item): string | null {
  if (item.thumbnail_url) return item.thumbnail_url;
  if (item.content_type === "image" && item.url) return item.url;
  return null;
}

export function ItemThumb({
  item,
  reason,
  onChange,
}: {
  item: Item;
  reason?: string;
  onChange?: (item: Item) => void;
}) {
  const [pending, start] = useTransition();
  const src = coverSrc(item);
  const typeLabel = TYPE_LABEL[item.content_type || ""] || null;

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
      className={`group flex flex-col overflow-hidden rounded-md bg-[var(--surface)]/80 transition-opacity duration-300 ${
        item.marks.is_read ? "opacity-60" : "opacity-100"
      } ${pending ? "opacity-70" : ""}`}
    >
      <Link href={`/items/${item.id}`} className="relative block aspect-[16/10] overflow-hidden bg-[var(--line)]">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt=""
            className="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-end bg-gradient-to-br from-[#c5d5cb] via-[#dfe8e2] to-[#b7c9bf] p-4">
            <span className="font-[family-name:var(--font-display)] text-2xl leading-none text-[var(--ink)]/25">
              {typeLabel || item.source_type}
            </span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-[var(--ink)]/70 to-transparent px-3 pb-2.5 pt-10">
          <p className="line-clamp-2 text-sm font-medium leading-snug text-white">{item.title || "无标题"}</p>
        </div>
      </Link>

      <div className="flex flex-1 flex-col gap-2 px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-[var(--muted)]">
          <span>{item.source_type}</span>
          {typeLabel ? <span>· {typeLabel}</span> : null}
        </div>
        {reason ? <p className="line-clamp-2 text-xs text-[var(--accent)]">{reason}</p> : null}
        <div className="mt-auto flex gap-3 text-xs">
          <button type="button" onClick={() => toggle("is_read")} className="text-[var(--muted)] hover:text-[var(--ink)]">
            {item.marks.is_read ? "标未读" : "已读"}
          </button>
          <button
            type="button"
            onClick={() => toggle("is_starred")}
            className="text-[var(--muted)] hover:text-[var(--ink)]"
          >
            {item.marks.is_starred ? "取消星标" : "星标"}
          </button>
        </div>
      </div>
    </article>
  );
}
