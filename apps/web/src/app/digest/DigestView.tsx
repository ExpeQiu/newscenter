"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type DigestVaultFile, type DigestVaultStatus } from "@/lib/api";
import { HtmlPreview, digestVaultRawUrl } from "@/components/HtmlPreview";

function formatMtime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

export default function DigestPage() {
  const [status, setStatus] = useState<DigestVaultStatus | null>(null);
  const [source, setSource] = useState<string>("all");
  const [files, setFiles] = useState<DigestVaultFile[]>([]);
  const [selected, setSelected] = useState<DigestVaultFile | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const openFile = useCallback((f: DigestVaultFile) => {
    setSelected(f);
    setErr(null);
    console.info("[digest] open source=%s path=%s", f.source_id, f.path);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const s = await api.digestVaultStatus();
      setStatus(s);
      console.info(
        "[digest] vault status readable=%s sources=%d",
        s.readable,
        s.sources.length
      );
      const list = await api.digestVaultFiles({
        source: source === "all" ? undefined : source,
        limit: 80,
      });
      setFiles(list.files);
      if (list.files.length) {
        openFile(list.files[0]);
      } else {
        setSelected(null);
      }
    } catch (e) {
      console.error("[digest] vault load failed", e);
      setErr(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [source, openFile]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sources = status?.sources ?? [];

  return (
    <div className="animate-fade-up space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">HTML Vault</p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--ink)] md:text-4xl">
          日报
        </h1>
        <p className="mt-3 max-w-xl text-sm text-[var(--body)]">
          按 <code className="text-xs">digest-sources.yml</code> 定义来源目录，直接读取其中的 HTML
          并展示（参考 AgentCenter 输出物）。
        </p>
      </header>

      {err ? <p className="text-sm text-red-700">{err}</p> : null}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="text-[var(--muted)]">
          来源{" "}
          <select
            className="ml-1 rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-[var(--ink)]"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="all">全部</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id} disabled={!s.readable}>
                {s.label}
                {!s.readable ? "（不可读）" : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="text-[var(--accent)] underline"
          onClick={() => void refresh()}
        >
          刷新
        </button>
        {status && !status.readable ? (
          <span className="text-[var(--muted)]">{status.message || "无可用来源"}</span>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
        <aside className="max-h-[78vh] overflow-y-auto rounded-md border border-[var(--line)] bg-[var(--surface)]/50">
          {loading ? (
            <p className="p-3 text-sm text-[var(--muted)]">加载中…</p>
          ) : files.length === 0 ? (
            <p className="p-3 text-sm text-[var(--muted)]">
              暂无 HTML。检查来源路径，或在 <code className="text-xs">daily/</code> 放入文件。
            </p>
          ) : (
            <ul className="divide-y divide-[var(--line)] text-sm">
              {files.map((f) => {
                const active =
                  selected?.source_id === f.source_id && selected?.path === f.path;
                return (
                  <li key={`${f.source_id}:${f.path}`}>
                    <button
                      type="button"
                      className={`block w-full px-3 py-2.5 text-left transition ${
                        active
                          ? "bg-[var(--accent)]/10 text-[var(--ink)]"
                          : "text-[var(--body)] hover:bg-[var(--surface)]"
                      }`}
                      onClick={() => void openFile(f)}
                    >
                      <span className="block truncate font-medium">{f.name}</span>
                      <span className="mt-0.5 block truncate text-xs text-[var(--muted)]">
                        {f.source_label} · {formatMtime(f.mtime)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        <section className="min-w-0 space-y-2">
          {selected ? (
            <p className="text-xs text-[var(--muted)]">
              {selected.source_label} · {selected.path} · {formatMtime(selected.mtime)}
            </p>
          ) : null}
          {selected ? (
            <HtmlPreview
              key={`${selected.source_id}:${selected.path}`}
              src={digestVaultRawUrl(selected.source_id, selected.path)}
              title={selected.name}
            />
          ) : (
            <div className="rounded-md bg-[var(--surface)] px-4 py-5 text-sm text-[var(--body)]">
              选择左侧 HTML 文件以预览。配置见仓库根目录{" "}
              <code className="text-xs">digest-sources.yml</code>。
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
