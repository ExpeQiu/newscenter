"use client";

import { useState, useTransition } from "react";
import type { Item } from "@/lib/api";
import { api } from "@/lib/api";

export function MarkBar({ item, onChange }: { item: Item; onChange: (i: Item) => void }) {
  const [pending, start] = useTransition();

  function patch(partial: Partial<Item["marks"]>) {
    start(async () => {
      const next = await api.patchMarks(item.id, partial);
      onChange(next);
    });
  }

  return (
    <div className={`flex flex-wrap gap-3 text-sm ${pending ? "opacity-60" : ""}`}>
      <button
        type="button"
        className="rounded-md border border-[var(--line)] px-3 py-1.5 hover:bg-[var(--surface)]"
        onClick={() => patch({ is_read: !item.marks.is_read })}
      >
        {item.marks.is_read ? "标未读" : "标已读"}
      </button>
      <button
        type="button"
        className="rounded-md border border-[var(--line)] px-3 py-1.5 hover:bg-[var(--surface)]"
        onClick={() => patch({ is_starred: !item.marks.is_starred })}
      >
        {item.marks.is_starred ? "取消星标" : "星标"}
      </button>
      <button
        type="button"
        className="rounded-md border border-[var(--line)] px-3 py-1.5 hover:bg-[var(--surface)]"
        onClick={() => patch({ is_archived: !item.marks.is_archived })}
      >
        {item.marks.is_archived ? "取消归档" : "归档"}
      </button>
    </div>
  );
}

export function AgentAskSheet({ itemId }: { itemId?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const res = await api.ask(q.trim(), itemId);
      setAnswer(res.answer);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-8 border-t border-[var(--line)] pt-6">
      <button
        type="button"
        className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起问 AI" : "问 AI"}
      </button>
      {open ? (
        <div className="mt-3 space-y-3 animate-in fade-in">
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            rows={3}
            placeholder="基于当前内容提问…"
            className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          <button
            type="button"
            disabled={loading}
            onClick={submit}
            className="rounded-md bg-[var(--ink)] px-4 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
          >
            {loading ? "思考中…" : "发送"}
          </button>
          {answer ? (
            <p className="whitespace-pre-wrap rounded-md bg-[var(--surface)] px-3 py-3 text-sm leading-relaxed text-[var(--body)]">
              {answer}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
