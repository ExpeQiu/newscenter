"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Note, type NoteColumn } from "@/lib/api";

export default function NotesView() {
  const [columns, setColumns] = useState<NoteColumn[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [newCol, setNewCol] = useState("");
  const [rename, setRename] = useState("");
  const [busy, setBusy] = useState(false);

  const loadNotes = useCallback(async (columnId: string) => {
    const res = await api.notes({ column_id: columnId, limit: 200 });
    setNotes(res.notes);
  }, []);

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const cols = await api.noteColumns();
      setColumns(cols.columns);
      const nextId =
        (activeId && cols.columns.some((c) => c.id === activeId) && activeId) ||
        cols.columns[0]?.id ||
        null;
      setActiveId(nextId);
      setRename(cols.columns.find((c) => c.id === nextId)?.name || "");
      if (nextId) await loadNotes(nextId);
      else setNotes([]);
      console.info("[notes] tab columns=%d active=%s", cols.count, nextId || "");
    } catch (e) {
      console.error("[notes] tab load failed", e);
      setErr(e instanceof Error ? e.message : "加载失败");
    }
  }, [activeId, loadNotes]);

  useEffect(() => {
    void refresh();
    // 仅首屏；栏目切换走 selectColumn
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectColumn(id: string) {
    setActiveId(id);
    setRename(columns.find((c) => c.id === id)?.name || "");
    try {
      await loadNotes(id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载摘录失败");
    }
  }

  async function addColumn() {
    const name = newCol.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      const col = await api.createNoteColumn(name);
      setNewCol("");
      const cols = await api.noteColumns();
      setColumns(cols.columns);
      await selectColumn(col.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "新建失败");
    } finally {
      setBusy(false);
    }
  }

  async function renameColumn() {
    if (!activeId || !rename.trim() || busy) return;
    setBusy(true);
    try {
      await api.patchNoteColumn(activeId, { name: rename.trim() });
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "改名失败");
    } finally {
      setBusy(false);
    }
  }

  async function removeColumn() {
    if (!activeId || busy) return;
    if (!confirm("删除栏目将同时删除其中摘录，确认？")) return;
    setBusy(true);
    try {
      await api.deleteNoteColumn(activeId);
      setActiveId(null);
      const cols = await api.noteColumns();
      setColumns(cols.columns);
      const next = cols.columns[0]?.id;
      if (next) await selectColumn(next);
      else setNotes([]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  async function removeNote(id: string) {
    try {
      await api.deleteNote(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
      setColumns((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? { ...c, note_count: Math.max(0, (c.note_count || 1) - 1) }
            : c
        )
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "删除摘录失败");
    }
  }

  const active = columns.find((c) => c.id === activeId);

  return (
    <div className="animate-fade-up space-y-6">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-3xl text-[var(--ink)]">笔记</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          在详情或日报中划选文字，右键加入栏目。与「收藏」星标互不影响。
        </p>
      </header>

      {err ? <p className="text-sm text-red-700">{err}</p> : null}

      <div className="grid gap-6 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
        <aside className="space-y-3">
          <ul className="rounded-md border border-[var(--line)] divide-y divide-[var(--line)] text-sm">
            {columns.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between px-3 py-2.5 text-left ${
                    c.id === activeId
                      ? "bg-[var(--accent)]/10 text-[var(--ink)] font-medium"
                      : "text-[var(--body)] hover:bg-[var(--surface)]"
                  }`}
                  onClick={() => void selectColumn(c.id)}
                >
                  <span className="truncate">{c.name}</span>
                  <span className="ml-2 text-xs text-[var(--muted)]">{c.note_count ?? 0}</span>
                </button>
              </li>
            ))}
            {columns.length === 0 ? (
              <li className="px-3 py-3 text-[var(--muted)]">暂无栏目</li>
            ) : null}
          </ul>
          <div className="flex gap-2">
            <input
              value={newCol}
              onChange={(e) => setNewCol(e.target.value)}
              placeholder="新栏目"
              className="min-w-0 flex-1 rounded-md border border-[var(--line)] bg-transparent px-2 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
              onKeyDown={(e) => {
                if (e.key === "Enter") void addColumn();
              }}
            />
            <button
              type="button"
              disabled={busy || !newCol.trim()}
              className="rounded-md border border-[var(--line)] px-2.5 py-1.5 text-sm disabled:opacity-50"
              onClick={() => void addColumn()}
            >
              添加
            </button>
          </div>
        </aside>

        <section className="min-w-0 space-y-4">
          {active ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <input
                value={rename || active.name}
                onChange={(e) => setRename(e.target.value)}
                onFocus={() => setRename(active.name)}
                className="rounded-md border border-[var(--line)] bg-transparent px-2 py-1.5 outline-none focus:border-[var(--accent)]"
              />
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-[var(--line)] px-2.5 py-1.5"
                onClick={() => void renameColumn()}
              >
                改名
              </button>
              <button
                type="button"
                disabled={busy || columns.length <= 1}
                className="rounded-md border border-[var(--line)] px-2.5 py-1.5 text-[var(--muted)] disabled:opacity-40"
                onClick={() => void removeColumn()}
              >
                删除栏目
              </button>
            </div>
          ) : null}

          <ul className="space-y-3">
            {notes.map((n) => (
              <li
                key={n.id}
                className="rounded-md border border-[var(--line)] bg-[var(--surface)]/40 px-4 py-3"
              >
                <blockquote className="whitespace-pre-wrap border-l-2 border-[var(--accent)]/40 pl-3 text-sm leading-relaxed text-[var(--body)]">
                  {n.quote_text}
                </blockquote>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--muted)]">
                  <span>
                    {n.source_kind === "item" && n.item_id ? (
                      <Link href={`/items/${n.item_id}`} className="text-[var(--accent)] underline">
                        {n.source_title || "原文"}
                      </Link>
                    ) : (
                      <Link href="/digest" className="text-[var(--accent)] underline">
                        {n.source_title || "日报"}
                      </Link>
                    )}
                    {n.created_at ? (
                      <span className="ml-2">
                        {new Date(n.created_at).toLocaleString("zh-CN", { hour12: false })}
                      </span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    className="text-[var(--muted)] hover:text-[var(--ink)]"
                    onClick={() => void removeNote(n.id)}
                  >
                    删除
                  </button>
                </div>
              </li>
            ))}
            {active && notes.length === 0 ? (
              <p className="text-sm text-[var(--muted)]">此栏目暂无摘录。去详情或日报划选添加。</p>
            ) : null}
          </ul>
        </section>
      </div>
    </div>
  );
}
