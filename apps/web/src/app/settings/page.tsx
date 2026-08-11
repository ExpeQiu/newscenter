"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; ai_provider: string } | null>(null);
  const [sources, setSources] = useState<{ id: string; name: string; type: string; enabled: boolean }[]>([]);
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [h, s] = await Promise.all([api.health(), api.sources()]);
    setHealth(h);
    setSources(s.sources);
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
        <p className="mt-2 text-sm text-[var(--muted)]">源开关、采集与 AI 批处理（轻量运维）。</p>
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

      <section>
        <h2 className="font-[family-name:var(--font-display)] text-xl">信源</h2>
        <ul className="mt-3 divide-y divide-[var(--line)]">
          {sources.map((s) => (
            <li key={s.id} className="flex items-center justify-between py-3 text-sm">
              <div>
                <div className="font-medium">{s.name}</div>
                <div className="text-[var(--muted)]">{s.type}</div>
              </div>
              <button
                type="button"
                className="rounded-md border border-[var(--line)] px-3 py-1"
                onClick={async () => {
                  await api.toggleSource(s.id, !s.enabled);
                  await refresh();
                }}
              >
                {s.enabled ? "已启用" : "已停用"}
              </button>
            </li>
          ))}
          {sources.length === 0 ? <li className="py-3 text-sm text-[var(--muted)]">尚无源记录，先跑采集。</li> : null}
        </ul>
      </section>
    </div>
  );
}
