"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type InsightEvent } from "@/lib/api";

const DIMENSIONS = [
  { v: "", l: "全部" },
  { v: "global", l: "全球" },
  { v: "china", l: "中国" },
  { v: "industry", l: "行业" },
  { v: "enterprise", l: "企业" },
];

const DIM_LABEL: Record<string, string> = {
  global: "全球",
  china: "中国",
  industry: "行业",
  enterprise: "企业",
};

function dayKey(iso?: string | null): string {
  if (!iso) return "未知日期";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export default function EventsView() {
  const [events, setEvents] = useState<InsightEvent[]>([]);
  const [dimension, setDimension] = useState("");
  const [industry, setIndustry] = useState("");
  const [industryOptions, setIndustryOptions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load(dim = dimension, ind = industry) {
    setLoading(true);
    setError(null);
    try {
      const data = await api.events({
        dimension: dim || undefined,
        industry: dim === "industry" && ind ? ind : undefined,
        limit: 100,
      });
      setEvents(data.events);
      if (dim === "industry" && !ind) {
        const set = new Set<string>();
        for (const e of data.events) {
          if (e.industry) set.add(e.industry);
        }
        setIndustryOptions(Array.from(set).sort());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, InsightEvent[]>();
    for (const e of events) {
      const k = dayKey(e.occurred_at);
      const list = map.get(k) || [];
      list.push(e);
      map.set(k, list);
    }
    return Array.from(map.entries());
  }, [events]);

  return (
    <div className="animate-fade-up">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">事件</h1>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <p className="text-sm text-[var(--muted)]">按时间轴浏览全球 / 中国 / 行业 / 企业重要事件</p>
        <button
          type="button"
          disabled={loading}
          onClick={() => {
            void api
              .runInsight({ force: true, kind: "event" })
              .then(() => load())
              .catch((e) => setError(e instanceof Error ? e.message : String(e)));
          }}
          className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs text-[var(--body)] disabled:opacity-50"
        >
          刷新检索
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        {DIMENSIONS.map((o) => (
          <button
            key={o.v || "all"}
            type="button"
            onClick={() => {
              setDimension(o.v);
              if (o.v !== "industry") setIndustry("");
              load(o.v, o.v === "industry" ? industry : "");
            }}
            className={`rounded-md px-3 py-1.5 ${
              dimension === o.v
                ? "bg-[var(--ink)] text-[var(--bg)]"
                : "bg-[var(--surface)] text-[var(--body)]"
            }`}
          >
            {o.l}
          </button>
        ))}
      </div>

      {dimension === "industry" && industryOptions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={() => {
              setIndustry("");
              load(dimension, "");
            }}
            className={`rounded-md px-3 py-1.5 ${
              !industry ? "bg-[var(--ink)] text-[var(--bg)]" : "bg-[var(--surface)] text-[var(--body)]"
            }`}
          >
            全部行业
          </button>
          {industryOptions.map((ind) => (
            <button
              key={ind}
              type="button"
              onClick={() => {
                setIndustry(ind);
                load(dimension, ind);
              }}
              className={`rounded-md px-3 py-1.5 ${
                industry === ind
                  ? "bg-[var(--ink)] text-[var(--bg)]"
                  : "bg-[var(--surface)] text-[var(--body)]"
              }`}
            >
              {ind}
            </button>
          ))}
        </div>
      )}

      {loading && <p className="mt-8 text-sm text-[var(--muted)]">加载中…</p>}
      {error && <p className="mt-8 text-sm text-red-600">{error}</p>}
      {!loading && !error && events.length === 0 && (
        <p className="mt-8 text-sm text-[var(--muted)]">
          暂无事件。请在本机运行{" "}
          <code className="rounded bg-[var(--surface)] px-1">newsc pipeline run insight --force</code>
          ，或确认 <code className="rounded bg-[var(--surface)] px-1">AI_MOCK_MODE=true</code>。
        </p>
      )}

      <div className="relative mt-8 space-y-8 border-l border-[var(--line)] pl-6">
        {grouped.map(([day, list]) => (
          <section key={day}>
            <h2 className="mb-4 -ml-6 flex items-center gap-2 text-sm font-medium text-[var(--muted)]">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
              {day}
            </h2>
            <ul className="space-y-5">
              {list.map((e) => (
                <li key={e.id} className="relative">
                  <span className="absolute -left-[1.7rem] top-1.5 h-2 w-2 rounded-full border border-[var(--line)] bg-[var(--bg)]" />
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                    <span>{DIM_LABEL[e.dimension] || e.dimension}</span>
                    {e.industry && <span>· {e.industry}</span>}
                    {e.entity && <span>· {e.entity}</span>}
                  </div>
                  <h3 className="mt-1 text-base font-medium text-[var(--ink)]">{e.title}</h3>
                  {e.summary && (
                    <p className="mt-1 text-sm leading-relaxed text-[var(--body)]">{e.summary}</p>
                  )}
                  {e.source_urls?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-3 text-xs">
                      {e.source_urls.map((u) => (
                        <a
                          key={u}
                          href={u}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[var(--accent)] underline-offset-2 hover:underline"
                        >
                          来源
                        </a>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
