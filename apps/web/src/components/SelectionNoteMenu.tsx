"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type NoteColumn } from "@/lib/api";

export type NoteSourceMeta = {
  source_kind: "item" | "digest";
  item_id?: string | null;
  digest_date?: string | null;
  source_title?: string;
  source_url?: string | null;
};

type MenuState = {
  x: number;
  y: number;
  quote: string;
  mode: "pick" | "create";
};

function selectedTextIn(root: HTMLElement | null): string {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return "";
  const text = sel.toString().trim();
  if (!text || !root) return "";
  const anchor = sel.anchorNode;
  if (!anchor || !root.contains(anchor)) return "";
  return text;
}

export function SelectionNoteMenu({
  children,
  source,
  className = "",
}: {
  children: ReactNode;
  source: NoteSourceMeta;
  className?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [columns, setColumns] = useState<NoteColumn[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [floatQuote, setFloatQuote] = useState<string | null>(null);

  const loadColumns = useCallback(async () => {
    const res = await api.noteColumns();
    setColumns(res.columns);
    return res.columns;
  }, []);

  const close = useCallback(() => {
    setMenu(null);
    setNewName("");
    setMsg(null);
  }, []);

  const openPicker = useCallback(
    async (quote: string, x: number, y: number) => {
      try {
        await loadColumns();
        setMenu({ x, y, quote, mode: "pick" });
        setMsg(null);
        console.info(
          "[notes] open_picker chars=%s source_kind=%s item_id=%s",
          quote.length,
          source.source_kind,
          source.item_id || ""
        );
      } catch (e) {
        console.error("[notes] load columns failed", e);
        setMsg(e instanceof Error ? e.message : "加载栏目失败");
      }
    },
    [loadColumns, source.item_id, source.source_kind]
  );

  const saveToColumn = useCallback(
    async (columnId: string, quote: string) => {
      setBusy(true);
      setMsg(null);
      try {
        const note = await api.createNote({
          column_id: columnId,
          quote_text: quote,
          source_kind: source.source_kind,
          item_id: source.item_id,
          digest_date: source.digest_date,
          source_title: source.source_title || "",
          source_url: source.source_url,
        });
        console.info(
          "[notes] created note_id=%s column_id=%s source_kind=%s",
          note.id,
          note.column_id,
          note.source_kind
        );
        setMsg("已加入笔记");
        setFloatQuote(null);
        window.getSelection()?.removeAllRanges();
        setTimeout(() => close(), 700);
      } catch (e) {
        console.error("[notes] create failed", e);
        setMsg(e instanceof Error ? e.message : "保存失败");
      } finally {
        setBusy(false);
      }
    },
    [close, source]
  );

  const createColumnAndSave = useCallback(async () => {
    const name = newName.trim();
    if (!name || !menu) return;
    setBusy(true);
    try {
      const col = await api.createNoteColumn(name);
      await saveToColumn(col.id, menu.quote);
    } catch (e) {
      console.error("[notes] create column failed", e);
      setMsg(e instanceof Error ? e.message : "新建栏目失败");
      setBusy(false);
    }
  }, [menu, newName, saveToColumn]);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;

    const onContext = (ev: MouseEvent) => {
      const quote = selectedTextIn(el);
      if (!quote) return;
      ev.preventDefault();
      void openPicker(quote, ev.clientX, ev.clientY);
    };

    const onMouseUp = () => {
      // 触控 / 无右键：划选后显示浮动条
      const coarse =
        typeof window !== "undefined" &&
        window.matchMedia &&
        window.matchMedia("(pointer: coarse)").matches;
      if (!coarse) return;
      const quote = selectedTextIn(el);
      setFloatQuote(quote || null);
    };

    el.addEventListener("contextmenu", onContext);
    el.addEventListener("mouseup", onMouseUp);
    el.addEventListener("touchend", onMouseUp);
    return () => {
      el.removeEventListener("contextmenu", onContext);
      el.removeEventListener("mouseup", onMouseUp);
      el.removeEventListener("touchend", onMouseUp);
    };
  }, [openPicker]);

  useEffect(() => {
    if (!menu && !floatQuote) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        close();
        setFloatQuote(null);
      }
    };
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as Node;
      if (rootRef.current?.contains(t)) return;
      const pop = document.getElementById("selection-note-pop");
      if (pop?.contains(t)) return;
      close();
      setFloatQuote(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [close, floatQuote, menu]);

  return (
    <div ref={rootRef} className={className || undefined}>
      {children}

      {floatQuote ? (
        <div
          id="selection-note-float"
          className="fixed bottom-20 left-1/2 z-50 -translate-x-1/2 md:bottom-8"
        >
          <button
            type="button"
            className="rounded-md bg-[var(--ink)] px-4 py-2 text-sm text-[var(--bg)] shadow-md"
            onClick={(e) => {
              e.stopPropagation();
              const rect = (e.target as HTMLElement).getBoundingClientRect();
              void openPicker(floatQuote, rect.left, rect.top - 8);
            }}
          >
            加入笔记
          </button>
        </div>
      ) : null}

      {menu ? (
        <div
          id="selection-note-pop"
          className="fixed z-50 min-w-[12rem] max-w-[18rem] rounded-md border border-[var(--line)] bg-[var(--bg)] py-1 text-sm shadow-lg"
          style={{
            left: Math.min(menu.x, typeof window !== "undefined" ? window.innerWidth - 200 : menu.x),
            top: Math.min(menu.y, typeof window !== "undefined" ? window.innerHeight - 240 : menu.y),
          }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="border-b border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)]">
            添加到笔记
          </div>
          {menu.mode === "pick" ? (
            <>
              <ul className="max-h-48 overflow-y-auto py-1">
                {columns.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      disabled={busy}
                      className="block w-full px-3 py-1.5 text-left text-[var(--ink)] hover:bg-[var(--surface)] disabled:opacity-50"
                      onClick={() => void saveToColumn(c.id, menu.quote)}
                    >
                      {c.name}
                    </button>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="block w-full border-t border-[var(--line)] px-3 py-1.5 text-left text-[var(--accent)] hover:bg-[var(--surface)]"
                onClick={() => setMenu({ ...menu, mode: "create" })}
              >
                新建栏目…
              </button>
            </>
          ) : (
            <div className="space-y-2 px-3 py-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="栏目名"
                className="w-full rounded border border-[var(--line)] bg-transparent px-2 py-1 text-sm outline-none focus:border-[var(--accent)]"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void createColumnAndSave();
                }}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy || !newName.trim()}
                  className="rounded bg-[var(--ink)] px-2.5 py-1 text-xs text-[var(--bg)] disabled:opacity-50"
                  onClick={() => void createColumnAndSave()}
                >
                  创建并加入
                </button>
                <button
                  type="button"
                  className="text-xs text-[var(--muted)]"
                  onClick={() => setMenu({ ...menu, mode: "pick" })}
                >
                  返回
                </button>
              </div>
            </div>
          )}
          {msg ? (
            <p className="border-t border-[var(--line)] px-3 py-1.5 text-xs text-[var(--body)]">{msg}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
