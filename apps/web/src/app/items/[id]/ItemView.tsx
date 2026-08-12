"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Item } from "@/lib/api";
import { ItemBody } from "@/components/ItemBody";
import { ItemSummary } from "@/components/ItemSummary";
import { VideoEmbed } from "@/components/VideoEmbed";
import { AgentAskSheet, MarkBar } from "@/components/MarkBar";
import { formatCount, formatPublishedAt } from "@/lib/format";
import { unwrapSummary } from "@/lib/formatSummary";

export default function ItemView({ id }: { id: string }) {
  const [item, setItem] = useState<Item | null>(null);
  const [cat, setCat] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMsg, setAiMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.item(id).then((i) => {
      setItem(i);
      setCat(i.ai_category || "");
    });
  }, [id]);

  async function runItemAi(force: boolean) {
    if (!item || aiBusy) return;
    setAiBusy(true);
    setAiMsg(force ? "正在重新生成…" : "正在生成摘要与分类…");
    console.info("[item] ai_process start id=%s force=%s", item.id, force);
    try {
      const r = await api.processItemAi(item.id, force);
      setItem(r.item);
      setCat(r.item.ai_category || "");
      if (r.failed > 0 && !(r.item.summary || "").trim()) {
        setAiMsg(`处理失败（provider=${r.provider}）。请检查 AI 配置后重试。`);
      } else if (!(r.item.summary || "").trim() && r.processed === 0) {
        setAiMsg("无待处理任务。可点「重新生成」强制跑一遍。");
      } else {
        setAiMsg(
          r.item.summary
            ? `完成（${r.provider}${r.processed ? ` · ${r.processed} 任务` : ""}）`
            : `已处理 ${r.processed} 任务，仍无摘要`
        );
      }
      console.info(
        "[item] ai_process done id=%s processed=%s failed=%s has_summary=%s",
        item.id,
        r.processed,
        r.failed,
        Boolean(r.item.summary)
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "AI 处理失败";
      setAiMsg(msg);
      console.error("[item] ai_process failed", e);
    } finally {
      setAiBusy(false);
    }
  }

  if (!item) {
    return <p className="text-sm text-[var(--muted)]">加载中…</p>;
  }

  const meta = item.meta || {};
  const published = formatPublishedAt(item.published_at);
  const play = formatCount(meta.play);
  const comment = formatCount(meta.comment);
  const author = typeof meta.author === "string" && meta.author.trim() ? meta.author.trim() : null;
  const duration = typeof meta.duration === "string" && meta.duration.trim() ? meta.duration.trim() : null;
  const facts = [
    author,
    published,
    play ? `${play} 播放` : null,
    comment ? `${comment} 评论` : null,
    duration,
  ].filter(Boolean) as string[];
  const hasSummary = Boolean(unwrapSummary(item.summary || ""));

  return (
    <article className="animate-fade-up w-full">
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
      {facts.length ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[var(--muted)]">
          {facts.map((f, i) => (
            <span key={`${f}-${i}`} className="inline-flex items-center gap-2">
              {i > 0 ? <span aria-hidden className="opacity-40">·</span> : null}
              {f}
            </span>
          ))}
        </p>
      ) : null}

      <section className="mt-6 w-full rounded-md bg-[var(--surface)]/80 px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">摘要</h2>
          <div className="flex flex-wrap items-center gap-2">
            {!hasSummary ? (
              <button
                type="button"
                disabled={aiBusy}
                onClick={() => void runItemAi(false)}
                className="rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                {aiBusy ? "处理中…" : "AI 生成"}
              </button>
            ) : (
              <button
                type="button"
                disabled={aiBusy}
                onClick={() => void runItemAi(true)}
                className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs text-[var(--body)] disabled:opacity-50"
              >
                {aiBusy ? "处理中…" : "重新生成"}
              </button>
            )}
          </div>
        </div>
        <ItemSummary summary={item.summary || ""} />
        {aiMsg ? (
          <p className={`mt-2 text-xs ${aiBusy ? "text-[var(--muted)]" : "text-[var(--body)]"}`}>
            {aiMsg}
          </p>
        ) : null}
      </section>

      {item.content_type === "video" && (item.embed_url || item.url) ? (
        <section className="mt-6 w-full">
          <VideoEmbed
            provider={item.embed_provider}
            embedUrl={item.embed_url}
            fallbackUrl={item.url}
            title={item.title}
          />
        </section>
      ) : null}

      {item.content_type === "image" && (item.thumbnail_url || item.url) ? (
        <section className="mt-6 w-full overflow-hidden rounded-md bg-[var(--surface)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={item.thumbnail_url || item.url || ""}
            alt={item.title}
            className="h-auto w-full object-cover"
          />
        </section>
      ) : null}

      {item.body ? (
        <section className="mt-8 w-full">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-xs uppercase tracking-[0.15em] text-[var(--muted)]">正文</h2>
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm text-[var(--accent)] underline underline-offset-2"
              >
                打开原文
              </a>
            ) : null}
          </div>
          <ItemBody body={item.body} />
        </section>
      ) : item.url ? (
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
