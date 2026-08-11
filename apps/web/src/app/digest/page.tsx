"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type DigestView = {
  date: string;
  html?: string | null;
  markdown?: string | null;
  source?: string | null;
  run_id?: string | null;
  empty: boolean;
};

export default function DigestPage() {
  const [digest, setDigest] = useState<DigestView | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const d = await api.digestToday();
        setDigest(d);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "加载失败");
      }
    })();
  }, []);

  const html = digest?.html?.trim() || null;

  return (
    <div className="animate-fade-up space-y-8">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">HTML Digest</p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--ink)] md:text-4xl">
          日报
        </h1>
        <p className="mt-3 max-w-xl text-sm text-[var(--body)]">
          展示由 OpenClaw / Hermes 通过 <code className="text-xs">newsc-digest push</code> 推送的
          HTML 日报。
        </p>
      </header>

      {err ? (
        <p className="text-sm text-red-700">
          API 不可用（{err}）。请先 <code className="text-xs">./scripts/start.sh</code>
        </p>
      ) : null}

      {digest && !digest.empty && html ? (
        <p className="text-xs text-[var(--muted)]">
          {digest.date}
          {digest.source ? ` · ${digest.source}` : ""}
          {digest.run_id ? ` · run ${digest.run_id.slice(0, 8)}` : ""}
        </p>
      ) : null}

      {!digest && !err ? (
        <p className="text-sm text-[var(--muted)]">加载中…</p>
      ) : html ? (
        <article
          className="prose-digest rounded-md bg-[var(--surface)]/70 px-4 py-5 text-[15px] leading-relaxed text-[var(--body)] [&_a]:text-[var(--accent)] [&_h1]:mb-3 [&_h1]:text-xl [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-lg [&_li]:my-0.5 [&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <div className="rounded-md bg-[var(--surface)] px-4 py-5 text-sm text-[var(--body)]">
          暂无 HTML 日报。用 CLI 推送后再刷新本页：
          <pre className="mt-3 overflow-x-auto rounded bg-[var(--bg)] px-3 py-2 text-xs text-[var(--ink)]">
            newsc-digest push --file report.html --source openclaw --format json
          </pre>
          <p className="mt-3">
            或去{" "}
            <Link href="/settings" className="text-[var(--accent)] underline">
              设置
            </Link>{" "}
            跑 Demo，或看{" "}
            <Link href="/" className="text-[var(--accent)] underline">
              今日
            </Link>{" "}
            的 markdown 洞察。
          </p>
        </div>
      )}
    </div>
  );
}
