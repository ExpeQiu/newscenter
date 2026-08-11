"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Item } from "@/lib/api";
import { VideoEmbed } from "@/components/VideoEmbed";
import { AgentAskSheet, MarkBar } from "@/components/MarkBar";

export default function ItemView({ id }: { id: string }) {
  const [item, setItem] = useState<Item | null>(null);
  const [cat, setCat] = useState("");

  useEffect(() => {
    if (!id) return;
    api.item(id).then((i) => {
      setItem(i);
      setCat(i.ai_category || "");
    });
  }, [id]);

  if (!item) {
    return <p className="text-sm text-[var(--muted)]">加载中…</p>;
  }

  return (
    <article className="animate-fade-up mx-auto max-w-2xl">
      <Link href="/feed" className="text-sm text-[var(--muted)] hover:text-[var(--ink)]">
        ← 返回浏览
      </Link>
      <div className="mt-4 text-xs uppercase tracking-wide text-[var(--muted)]">
        {item.source_type}
        {item.content_type ? ` · ${item.content_type}` : ""}
        {item.ai_category ? ` · ${item.ai_category}` : ""}
      </div>
      <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl leading-tight md:text-4xl">
        {item.title}
      </h1>

      <section className="mt-6 rounded-md bg-[var(--surface)]/80 px-4 py-4">
        <h2 className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">摘要</h2>
        <p className="mt-2 text-[16px] leading-relaxed text-[var(--ink)]">
          {item.summary || "摘要尚未生成，可在设置中触发 AI 处理。"}
        </p>
      </section>

      {item.content_type === "video" && (item.embed_url || item.url) ? (
        <section className="mt-6">
          <VideoEmbed
            provider={item.embed_provider}
            embedUrl={item.embed_url}
            fallbackUrl={item.url}
            title={item.title}
          />
        </section>
      ) : null}

      {item.content_type === "image" && (item.thumbnail_url || item.url) ? (
        <section className="mt-6 overflow-hidden rounded-md bg-[var(--surface)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={item.thumbnail_url || item.url || ""}
            alt={item.title}
            className="h-auto w-full object-cover"
          />
        </section>
      ) : null}

      {item.body ? (
        <section className="mt-6">
          <h2 className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">正文</h2>
          <p className="mt-2 whitespace-pre-wrap text-[15px] leading-relaxed text-[var(--body)]">{item.body}</p>
        </section>
      ) : null}

      {item.url ? (
        <p className="mt-4 text-sm">
          <a href={item.url} target="_blank" rel="noreferrer" className="text-[var(--accent)] underline">
            打开原文
          </a>
        </p>
      ) : null}

      <section className="mt-8 space-y-3">
        <MarkBar item={item} onChange={setItem} />
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input
            value={cat}
            onChange={(e) => setCat(e.target.value)}
            placeholder="分类"
            className="rounded-md border border-[var(--line)] bg-transparent px-2 py-1.5"
          />
          <button
            type="button"
            className="rounded-md border border-[var(--line)] px-3 py-1.5"
            onClick={async () => {
              if (!cat.trim()) return;
              const next = await api.patchCategory(item.id, cat.trim(), true);
              setItem(next);
            }}
          >
            锁定分类
          </button>
          <div className="flex gap-2 text-[var(--muted)]">
            {item.tags.map((t) => (
              <span key={`${t.origin}-${t.name}`}>#{t.name}</span>
            ))}
          </div>
        </div>
      </section>

      <AgentAskSheet itemId={item.id} />
    </article>
  );
}
