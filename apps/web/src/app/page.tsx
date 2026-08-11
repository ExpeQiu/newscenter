"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Item } from "@/lib/api";
import { ItemCard } from "@/components/ItemCard";

export default function TodayPage() {
  const [digest, setDigest] = useState<{
    markdown: string | null;
    html?: string | null;
    empty: boolean;
    date: string;
  } | null>(null);
  const [recs, setRecs] = useState<{ score: number; reason: string; item: Item }[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [d, r] = await Promise.all([api.digestToday(), api.recommendations()]);
        setDigest(d);
        setRecs(r.items);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "加载失败");
      }
    })();
  }, []);

  return (
    <div className="animate-fade-up space-y-10">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Daily Insight</p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl text-[var(--ink)] md:text-5xl">
          NewsC
        </h1>
        <p className="mt-3 max-w-xl text-[var(--body)]">每日一站，洞察全网。摘要先行，再决定深挖。</p>
      </header>

      {err ? (
        <p className="text-sm text-red-700">
          API 不可用（{err}）。请先 <code className="text-xs">./scripts/start.sh</code>
        </p>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-[family-name:var(--font-display)] text-2xl">今日洞察</h2>
          <Link href="/digest" className="text-sm text-[var(--accent)] underline">
            HTML 日报
          </Link>
        </div>
        {!digest ? (
          <p className="text-sm text-[var(--muted)]">加载中…</p>
        ) : digest.empty || !digest.markdown ? (
          <div className="rounded-md bg-[var(--surface)] px-4 py-5 text-sm text-[var(--body)]">
            暂无洞察。去{" "}
            <Link href="/settings" className="text-[var(--accent)] underline">
              设置
            </Link>{" "}
            跑一次采集与 AI 处理；CLI 推送的 HTML 见{" "}
            <Link href="/digest" className="text-[var(--accent)] underline">
              日报
            </Link>
            。
          </div>
        ) : (
          <article className="prose-digest whitespace-pre-wrap rounded-md bg-[var(--surface)]/70 px-4 py-5 text-[15px] leading-relaxed text-[var(--body)]">
            {digest.markdown}
          </article>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-[family-name:var(--font-display)] text-2xl">今日荐读</h2>
        {recs.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">暂无推荐。</p>
        ) : (
          <div>
            {recs.map((r) => (
              <ItemCard
                key={r.item.id}
                item={r.item}
                reason={r.reason}
                onChange={(next) =>
                  setRecs((prev) => prev.map((x) => (x.item.id === next.id ? { ...x, item: next } : x)))
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
