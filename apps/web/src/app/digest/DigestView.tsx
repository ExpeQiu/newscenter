"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type DigestVaultFile, type DigestVaultStatus } from "@/lib/api";
import { SelectableDigestHtml } from "@/components/HtmlPreview";
import { SelectionNoteMenu } from "@/components/SelectionNoteMenu";

function formatMtime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

type DateRange = "all" | "today" | "week" | "month";

const DATE_RANGE_OPTIONS: { id: Exclude<DateRange, "all">; label: string }[] = [
  { id: "today", label: "今天" },
  { id: "week", label: "本周" },
  { id: "month", label: "本月" },
];

function startOfLocalDay(d = new Date()): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** 按本机时区判断文件 mtime 是否落在快捷日期范围内 */
function inDateRange(mtimeIso: string, range: DateRange): boolean {
  if (range === "all") return true;
  const ts = new Date(mtimeIso).getTime();
  if (Number.isNaN(ts)) return false;
  const now = new Date();
  const today0 = startOfLocalDay(now);
  if (range === "today") return ts >= today0.getTime();
  if (range === "week") {
    const dow = today0.getDay(); // 0=周日
    const mondayOffset = dow === 0 ? -6 : 1 - dow;
    const week0 = new Date(today0);
    week0.setDate(today0.getDate() + mondayOffset);
    return ts >= week0.getTime();
  }
  const month0 = new Date(now.getFullYear(), now.getMonth(), 1);
  return ts >= month0.getTime();
}

export default function DigestPage() {
  const [status, setStatus] = useState<DigestVaultStatus | null>(null);
  const [source, setSource] = useState<string>("all");
  const [dateRange, setDateRange] = useState<DateRange>("all");
  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [files, setFiles] = useState<DigestVaultFile[]>([]);
  const [selected, setSelected] = useState<DigestVaultFile | null>(null);
  const [html, setHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false);

  const openFile = useCallback(async (f: DigestVaultFile) => {
    setSelected(f);
    setErr(null);
    setHtml("");
    console.info("[digest] open source=%s path=%s", f.source_id, f.path);
    try {
      const doc = await api.digestVaultFile(f.source_id, f.path);
      setHtml(doc.html || "");
    } catch (e) {
      console.error("[digest] load html failed", e);
      setErr(e instanceof Error ? e.message : "加载 HTML 失败");
    }
  }, []);

  const toggleTag = useCallback((t: string) => {
    setActiveTags((prev) => {
      if (prev.includes(t)) {
        const next = prev.filter((x) => x !== t);
        console.info("[digest] tag off=%s active=%s", t, next.join(",") || "(none)");
        return next;
      }
      const next = [...prev, t];
      console.info("[digest] tag on=%s active=%s", t, next.join(","));
      return next;
    });
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
      let filtered = list.files;
      if (activeTags.length > 0) {
        filtered = filtered.filter((f) => {
          const src = s.sources.find((x) => x.id === f.source_id);
          const srcTags = src?.tags || [];
          return activeTags.some((t) => srcTags.includes(t));
        });
      }
      if (dateRange !== "all") {
        filtered = filtered.filter((f) => inDateRange(f.mtime, dateRange));
      }
      console.info(
        "[digest] files source=%s date=%s tags=%s raw=%d filtered=%d",
        source,
        dateRange,
        activeTags.join(",") || "(all)",
        list.files.length,
        filtered.length
      );
      setFiles(filtered);
      if (filtered.length) {
        await openFile(filtered[0]);
      } else {
        setSelected(null);
        setHtml("");
      }
    } catch (e) {
      console.error("[digest] vault load failed", e);
      setErr(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [source, dateRange, activeTags, openFile]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sources = status?.sources ?? [];
  const allTags = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const s of sources) {
      for (const t of s.tags || []) {
        if (!t || seen.has(t)) continue;
        seen.add(t);
        out.push(t);
      }
    }
    return out;
  }, [sources]);

  // 配置里已删除的标签，从选中态清掉
  useEffect(() => {
    const known = new Set(allTags);
    setActiveTags((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.filter((t) => known.has(t));
      return next.length === prev.length ? prev : next;
    });
  }, [allTags]);

  const digestDate = selected?.mtime ? selected.mtime.slice(0, 10) : null;

  return (
    <div className="animate-fade-up space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">HTML Vault</p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--ink)] md:text-4xl">
          日报
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-[var(--body)]">
          按 <code className="text-xs">digest-sources.yml</code> 定义来源目录，直接读取其中的 HTML
          并按原文样式展示。划选文字后右键可加入笔记。
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
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[var(--muted)]">日期</span>
          {DATE_RANGE_OPTIONS.map((opt) => {
            const on = dateRange === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                aria-pressed={on}
                className={`rounded border px-2.5 py-1 transition ${
                  on
                    ? "border-[var(--ink)] bg-[var(--ink)] text-[var(--bg)]"
                    : "border-[var(--line)] bg-[var(--surface)] text-[var(--body)] hover:border-[var(--ink)]/40"
                }`}
                onClick={() => {
                  const next: DateRange = on ? "all" : opt.id;
                  console.info("[digest] date range=%s", next);
                  setDateRange(next);
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
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

      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-[var(--muted)]">标签</span>
          {allTags.map((t) => {
            const on = activeTags.includes(t);
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                className={`rounded border px-2.5 py-1 transition ${
                  on
                    ? "border-[var(--ink)] bg-[var(--ink)] text-[var(--bg)]"
                    : "border-[var(--line)] bg-[var(--surface)] text-[var(--body)] hover:border-[var(--ink)]/40"
                }`}
                onClick={() => toggleTag(t)}
              >
                {t}
              </button>
            );
          })}
          {activeTags.length > 0 ? (
            <button
              type="button"
              className="text-xs text-[var(--muted)] underline"
              onClick={() => {
                console.info("[digest] clear tags");
                setActiveTags([]);
              }}
            >
              清除
            </button>
          ) : null}
        </div>
      ) : null}

      <div
        className={`grid gap-6 ${
          listOpen ? "lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]" : ""
        }`}
      >
        <aside className="rounded-md border border-[var(--line)] bg-[var(--surface)]/50">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm"
            aria-expanded={listOpen}
            onClick={() => {
              const next = !listOpen;
              console.info("[digest] file list %s", next ? "open" : "close");
              setListOpen(next);
            }}
          >
            <span className="min-w-0 truncate text-[var(--ink)]">
              {selected ? selected.name : "文件列表"}
              {!loading ? (
                <span className="ml-1.5 text-[var(--muted)]">({files.length})</span>
              ) : null}
            </span>
            <span className="shrink-0 text-xs text-[var(--muted)]">
              {listOpen ? "收起" : "展开"}
            </span>
          </button>
          {listOpen ? (
            <div className="max-h-[78vh] overflow-y-auto border-t border-[var(--line)]">
              {loading ? (
                <p className="p-3 text-sm text-[var(--muted)]">加载中…</p>
              ) : files.length === 0 ? (
                <p className="p-3 text-sm text-[var(--muted)]">
                  暂无 HTML。检查来源路径，或在 <code className="text-xs">daily/</code>{" "}
                  放入文件。
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
            </div>
          ) : null}
        </aside>

        <section className="min-w-0 space-y-2">
          {selected ? (
            <p className="text-xs text-[var(--muted)]">
              {selected.source_label} · {selected.path} · {formatMtime(selected.mtime)}
            </p>
          ) : null}
          {selected && html ? (
            <SelectionNoteMenu
              source={{
                source_kind: "digest",
                digest_date: digestDate,
                source_title: selected.name || selected.path,
                source_url: `/digest`,
              }}
            >
              <SelectableDigestHtml
                key={`${selected.source_id}:${selected.path}`}
                html={html}
                title={selected.name}
                className="max-h-[78vh] overflow-y-auto"
              />
            </SelectionNoteMenu>
          ) : selected ? (
            <p className="text-sm text-[var(--muted)]">加载正文…</p>
          ) : (
            <div className="rounded-md bg-[var(--surface)] px-4 py-5 text-sm text-[var(--body)]">
              展开左侧文件列表以选择预览。配置见仓库根目录{" "}
              <code className="text-xs">digest-sources.yml</code>。
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
