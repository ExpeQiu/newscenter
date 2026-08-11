"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; ai_provider: string } | null>(null);
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const h = await api.health();
    setHealth(h);
  }

  useEffect(() => {
    refresh().catch(console.error);
  }, []);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setLog(`${label}…`);
    try {
      const r = await fn();
      setLog(`${label} 完成：${JSON.stringify(r)}`);
      await refresh();
    } catch (e) {
      setLog(`${label} 失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="animate-fade-up max-w-xl space-y-8">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-3xl">设置</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          系统状态与采集运维。信源请到{" "}
          <Link href="/subscribe" className="text-[var(--accent)] underline-offset-2 hover:underline">
            订阅
          </Link>{" "}
          管理。
        </p>
      </header>

      <section className="rounded-md bg-[var(--surface)] px-4 py-3 text-sm">
        <div>API：{health?.ok ? "正常" : "未知"}</div>
        <div>AI Provider：{health?.ai_provider ?? "—"}</div>
      </section>

      <section className="space-y-2">
        <h2 className="font-[family-name:var(--font-display)] text-xl">一键演示</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            onClick={() => run("采集 all-demo", () => api.runPipeline("all-demo"))}
          >
            采集 Demo
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
            onClick={() => run("AI 批处理", () => api.processAi())}
          >
            处理 AI Jobs
          </button>
        </div>
        {log ? <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-[var(--body)]">{log}</pre> : null}
      </section>
    </div>
  );
}
