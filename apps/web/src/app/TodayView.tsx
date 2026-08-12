"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Item } from "@/lib/api";
import { DigestMarkdown } from "@/components/DigestMarkdown";
import { HtmlPreview } from "@/components/HtmlPreview";
import { ItemThumb } from "@/components/ItemThumb";

export default function TodayPage() {
  const [digest, setDigest] = useState<{
    markdown: string | null;
    html?: string | null;
    empty: boolean;
    date: string;
    synthesized?: boolean;
    vault?: { count?: number; source_label?: string; path?: string } | null;
  } | null>(null);
  const [recs, setRecs] = useState<{ score: number; reason: string; item: Item }[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [d, r] = await Promise.all([api.digestToday(), api.recommendations()]);
        setDigest(d);
        setRecs(r.items);
        console.info(
          "[today] digest empty=%s synthesized=%s md=%s html=%s vault=%s recs=%d fallback=%s",
          d.empty,
          Boolean(d.synthesized),
          (d.markdown || "").length,
          (d.html || "").length,
          d.vault?.count ?? 0,
          r.items.length,
          Boolean(r.fallback)
        );
      } catch (e) {
        setErr(e instanceof Error ? e.message : "加载失败");
      }
    })();
  }, []);

  return (
    <div className="animate-fade-up space-y-10">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">NewsC</p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl text-[var(--ink)] md:text-5xl">
          信息中心
        </h1>
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
            HTML 日报（目录直读）
          </Link>
        </div>
        {!digest ? (
          <p className="text-sm text-[var(--muted)]">加载中…</p>
        ) : digest.empty || (!digest.markdown && !digest.html) ? (
          <div className="rounded-md bg-[var(--surface)] px-4 py-5 text-sm text-[var(--body)]">
            暂无洞察。去{" "}
            <Link href="/settings" className="text-[var(--accent)] underline">
              设置
            </Link>{" "}
            跑一次采集与 AI 处理；目录 HTML 见{" "}
            <Link href="/digest" className="text-[var(--accent)] underline">
              日报
            </Link>
            。
          </div>
        ) : digest.markdown ? (
          <DigestMarkdown
            content={digest.markdown}
            className="rounded-md bg-[var(--surface)]/70 px-4 py-5 text-[15px] leading-relaxed"
          />
        ) : (
          <HtmlPreview content={digest.html} title={`今日洞察 · ${digest.date}`} />
        )}
      </section>

      <section>
        <h2 className="mb-4 font-[family-name:var(--font-display)] text-2xl">今日荐读</h2>
        {recs.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            暂无推荐。去{" "}
            <Link href="/settings" className="text-[var(--accent)] underline">
              设置
            </Link>{" "}
            跑采集与 AI 处理后刷新。
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recs.map((r) => (
              <ItemThumb
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
