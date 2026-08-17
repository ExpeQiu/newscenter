"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type MacroSnapshotItem } from "@/lib/api";

const SCOPES = [
  { v: "", l: "全部" },
  { v: "global", l: "全球" },
  { v: "china", l: "中国" },
  { v: "industry", l: "行业" },
];

const SCOPE_LABEL: Record<string, string> = {
  global: "全球",
  china: "中国",
  industry: "行业",
};

function formatValue(item: MacroSnapshotItem): string {
  const latest = item.latest;
  if (!latest) return "—";
  if (latest.value_text) return latest.value_text;
  if (latest.value != null) {
    const u = item.unit || "";
    const n = Number.isInteger(latest.value)
      ? String(latest.value)
      : String(Math.round(latest.value * 100) / 100);
    return `${n}${u}`;
  }
  return "—";
}

function historyNums(item: MacroSnapshotItem): number[] {
  return item.history.map((h) => h.value).filter((v): v is number => typeof v === "number");
}

function deltaVsPrev(item: MacroSnapshotItem): {
  text: string;
  dir: "up" | "down" | "flat" | null;
} {
  const hist = historyNums(item);
  if (hist.length < 2) return { text: "", dir: null };
  const prev = hist[hist.length - 2];
  const cur = hist[hist.length - 1];
  const d = cur - prev;
  if (Math.abs(d) < 1e-9) return { text: "持平", dir: "flat" };
  const sign = d > 0 ? "+" : "";
  const rounded = Math.round(d * 100) / 100;
  return {
    text: `${sign}${rounded}`,
    dir: d > 0 ? "up" : "down",
  };
}

/** 块内自适应面积图（viewBox 缩放填满容器） */
function ScaleChart({
  values,
  up,
  className = "",
}: {
  values: number[];
  up?: boolean | null;
  className?: string;
}) {
  if (values.length === 0) {
    return <div className={`bg-[var(--surface)]/40 ${className}`} aria-hidden />;
  }

  const w = 320;
  const h = 120;
  const padY = 8;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  const xs = values.map((_, i) => (values.length === 1 ? w / 2 : (i / (values.length - 1)) * w));
  const ys = values.map((v) => h - padY - ((v - min) / span) * (h - padY * 2));

  const line = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;

  const stroke =
    up === true ? "var(--accent)" : up === false ? "#9a4a3a" : "var(--muted)";
  const fill =
    up === true
      ? "color-mix(in srgb, var(--accent) 22%, transparent)"
      : up === false
        ? "color-mix(in srgb, #9a4a3a 18%, transparent)"
        : "color-mix(in srgb, var(--muted) 16%, transparent)";

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className={`block h-full w-full ${className}`}
      aria-hidden
    >
      <path d={area} fill={fill} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {values.length > 0 && (
        <circle
          cx={xs[xs.length - 1]}
          cy={ys[ys.length - 1]}
          r="3.5"
          fill={stroke}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

function IndicatorBlock({
  item,
  active,
  onSelect,
}: {
  item: MacroSnapshotItem;
  active: boolean;
  onSelect: () => void;
}) {
  const nums = historyNums(item);
  const delta = deltaVsPrev(item);
  const up = delta.dir === "up" ? true : delta.dir === "down" ? false : null;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex min-h-[168px] flex-col overflow-hidden rounded-md border text-left transition-all ${
        active
          ? "border-[var(--accent)] bg-[var(--surface)] shadow-[0_0_0_1px_var(--accent)]"
          : "border-[var(--line)] bg-[var(--bg)]/60 hover:border-[var(--ink)]/25 hover:bg-[var(--surface)]/50"
      }`}
    >
      <div className="flex items-start justify-between gap-2 px-3.5 pt-3.5">
        <div className="min-w-0">
          <div className="text-[11px] tracking-wide text-[var(--muted)]">
            {SCOPE_LABEL[item.scope] || item.scope}
            {item.industry ? ` · ${item.industry}` : ""}
          </div>
          <div className="mt-0.5 line-clamp-2 text-sm font-medium leading-snug text-[var(--ink)]">
            {item.label}
          </div>
        </div>
        {delta.dir ? (
          <span
            className={`shrink-0 text-xs tabular-nums ${
              delta.dir === "up"
                ? "text-[var(--accent)]"
                : delta.dir === "down"
                  ? "text-[#9a4a3a]"
                  : "text-[var(--muted)]"
            }`}
          >
            {delta.dir === "up" ? "↑" : delta.dir === "down" ? "↓" : "→"}
            {delta.text}
          </span>
        ) : null}
      </div>

      <div className="mt-2 px-3.5">
        <div className="font-[family-name:var(--font-display)] text-[1.75rem] leading-none tracking-tight tabular-nums text-[var(--ink)]">
          {formatValue(item)}
        </div>
        {item.latest?.period_label ? (
          <div className="mt-1 text-[11px] tabular-nums text-[var(--muted)]">{item.latest.period_label}</div>
        ) : null}
      </div>

      <div className="mt-auto h-[72px] w-full pt-2">
        <ScaleChart values={nums} up={up} />
      </div>
    </button>
  );
}

function DetailPanel({ active }: { active: MacroSnapshotItem }) {
  const nums = historyNums(active);
  const delta = deltaVsPrev(active);
  const up = delta.dir === "up" ? true : delta.dir === "down" ? false : null;

  return (
    <aside className="overflow-hidden rounded-md border border-[var(--line)] bg-[var(--bg)]/80">
      <div className="h-28 w-full border-b border-[var(--line)]">
        <ScaleChart values={nums} up={up} />
      </div>
      <div className="p-4 text-sm">
        <div className="text-xs tracking-wide text-[var(--muted)]">
          {SCOPE_LABEL[active.scope] || active.scope}
          {active.industry ? ` · ${active.industry}` : ""}
        </div>
        <h2 className="mt-1 font-[family-name:var(--font-display)] text-xl leading-snug text-[var(--ink)]">
          {active.label}
        </h2>
        <div className="mt-3 flex items-end gap-3">
          <div className="font-[family-name:var(--font-display)] text-3xl tabular-nums tracking-tight text-[var(--ink)]">
            {formatValue(active)}
          </div>
          {delta.dir ? (
            <span
              className={`mb-1 text-sm tabular-nums ${
                delta.dir === "up"
                  ? "text-[var(--accent)]"
                  : delta.dir === "down"
                    ? "text-[#9a4a3a]"
                    : "text-[var(--muted)]"
              }`}
            >
              {delta.dir === "up" ? "↑" : delta.dir === "down" ? "↓" : "→"} {delta.text}
            </span>
          ) : null}
        </div>
        {active.latest?.period_label ? (
          <div className="mt-1 text-xs text-[var(--muted)]">期别 {active.latest.period_label}</div>
        ) : null}
        {active.description && (
          <p className="mt-3 leading-relaxed text-[var(--body)]">{active.description}</p>
        )}
        <div className="mt-5 text-xs tracking-wide text-[var(--muted)]">历史观测</div>
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr className="text-[var(--muted)]">
              <th className="py-1 font-normal">期别</th>
              <th className="py-1 text-right font-normal">数值</th>
            </tr>
          </thead>
          <tbody>
            {[...active.history].reverse().map((h) => (
              <tr key={h.id} className="border-t border-[var(--line)]">
                <td className="py-2 text-[var(--body)]">
                  {h.period_label || h.observed_at?.slice(0, 10) || "—"}
                </td>
                <td className="py-2 text-right tabular-nums text-[var(--ink)]">
                  {h.value_text || (h.value != null ? `${h.value}${active.unit || ""}` : "—")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {active.latest?.source_urls?.length ? (
          <div className="mt-4 flex flex-wrap gap-3 text-xs">
            {active.latest.source_urls.map((u) => (
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
        ) : null}
      </div>
    </aside>
  );
}

function groupByScope(items: MacroSnapshotItem[]): { key: string; label: string; rows: MacroSnapshotItem[] }[] {
  const order = ["china", "global", "industry"];
  const map = new Map<string, MacroSnapshotItem[]>();
  for (const it of items) {
    const k = it.scope || "other";
    const list = map.get(k) || [];
    list.push(it);
    map.set(k, list);
  }
  const keys = [
    ...order.filter((k) => map.has(k)),
    ...Array.from(map.keys()).filter((k) => !order.includes(k)),
  ];
  return keys.map((key) => ({
    key,
    label: SCOPE_LABEL[key] || key,
    rows: map.get(key) || [],
  }));
}

/** 「全部」：中国综合 / 金融 / 全球；不含 industry scope */
function groupAllView(items: MacroSnapshotItem[]): { key: string; label: string; rows: MacroSnapshotItem[] }[] {
  const chinaCore: MacroSnapshotItem[] = [];
  const finance: MacroSnapshotItem[] = [];
  const global: MacroSnapshotItem[] = [];
  for (const it of items) {
    if (it.scope === "global") global.push(it);
    else if (it.scope === "china" && it.industry === "金融") finance.push(it);
    else if (it.scope === "china") chinaCore.push(it);
  }
  const out: { key: string; label: string; rows: MacroSnapshotItem[] }[] = [];
  if (chinaCore.length) out.push({ key: "china", label: "中国", rows: chinaCore });
  if (finance.length) out.push({ key: "finance", label: "金融", rows: finance });
  if (global.length) out.push({ key: "global", label: "全球", rows: global });
  return out;
}

/** 「行业」：按 industry 字段分组 */
function groupByIndustry(items: MacroSnapshotItem[]): { key: string; label: string; rows: MacroSnapshotItem[] }[] {
  const order = ["AI", "能源", "原材料", "房地产", "金融", "半导体"];
  const map = new Map<string, MacroSnapshotItem[]>();
  for (const it of items) {
    const k = it.industry || "其他";
    const list = map.get(k) || [];
    list.push(it);
    map.set(k, list);
  }
  const keys = [
    ...order.filter((k) => map.has(k)),
    ...Array.from(map.keys()).filter((k) => !order.includes(k)).sort(),
  ];
  return keys.map((key) => ({
    key,
    label: key,
    rows: map.get(key) || [],
  }));
}

export default function DataView() {
  const [items, setItems] = useState<MacroSnapshotItem[]>([]);
  const [scope, setScope] = useState("");
  const [industry, setIndustry] = useState("");
  const [industryOptions, setIndustryOptions] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const active = items.find((i) => i.indicator_id === selected) || items[0] || null;
  const isAll = scope === "";
  const isIndustry = scope === "industry";
  // 「全部」只展示全球 + 中国宏观（含金融端），行业放到「行业」Tab
  const visibleItems = useMemo(
    () => (isAll ? items.filter((i) => i.scope !== "industry") : items),
    [items, isAll]
  );
  const groups = useMemo(() => {
    if (isAll) return groupAllView(visibleItems);
    if (isIndustry && !industry) return groupByIndustry(items);
    return groupByScope(items);
  }, [visibleItems, items, isAll, isIndustry, industry]);
  const activeVisible =
    visibleItems.find((i) => i.indicator_id === selected) || visibleItems[0] || null;

  async function load(sc = scope, ind = industry) {
    setLoading(true);
    setError(null);
    try {
      const data = await api.macroSnapshot({
        scope: sc || undefined,
        industry: sc === "industry" && ind ? ind : undefined,
      });
      setItems(data.items);
      if (sc === "industry" && !ind) {
        const set = new Set<string>();
        for (const it of data.items) {
          if (it.industry) set.add(it.industry);
        }
        setIndustryOptions(Array.from(set).sort());
      }
      if (data.items.length) {
        const pool = sc === "" ? data.items.filter((i) => i.scope !== "industry") : data.items;
        if (!pool.some((i) => i.indicator_id === selected)) {
          setSelected(pool[0]?.indicator_id ?? null);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="animate-fade-up">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">数据</h1>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <p className="text-sm text-[var(--muted)]">全球与中国宏观指标，以及特定行业数据</p>
        <button
          type="button"
          disabled={loading || refreshing}
          onClick={() => {
            setRefreshing(true);
            void api
              .runInsight({ force: true, kind: "macro" })
              .then(() => load())
              .catch((e) => setError(e instanceof Error ? e.message : String(e)))
              .finally(() => setRefreshing(false));
          }}
          className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs text-[var(--body)] disabled:opacity-50"
        >
          {refreshing ? "检索中…" : "刷新检索"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        {SCOPES.map((o) => (
          <button
            key={o.v || "all"}
            type="button"
            onClick={() => {
              setScope(o.v);
              if (o.v !== "industry") setIndustry("");
              load(o.v, o.v === "industry" ? industry : "");
            }}
            className={`rounded-md px-3 py-1.5 ${
              scope === o.v
                ? "bg-[var(--ink)] text-[var(--bg)]"
                : "bg-[var(--surface)] text-[var(--body)]"
            }`}
          >
            {o.l}
          </button>
        ))}
      </div>

      {scope === "industry" && industryOptions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={() => {
              setIndustry("");
              load(scope, "");
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
                load(scope, ind);
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
      {!loading && !error && items.length === 0 && (
        <p className="mt-8 text-sm text-[var(--muted)]">
          暂无数据。请运行{" "}
          <code className="rounded bg-[var(--surface)] px-1">newsc pipeline run insight --force</code>
          。
        </p>
      )}

      {/* 全部：中国 / 金融 / 全球；不含行业 scope */}
      {!loading && visibleItems.length > 0 && isAll && (
        <div className="mt-8 space-y-10">
          {groups.map((g) => (
            <section key={g.key}>
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="font-[family-name:var(--font-display)] text-lg tracking-tight text-[var(--ink)]">
                  {g.label}
                </h2>
                <span className="text-xs tabular-nums text-[var(--muted)]">{g.rows.length} 项</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {g.rows.map((it) => (
                  <IndicatorBlock
                    key={it.indicator_id}
                    item={it}
                    active={activeVisible?.indicator_id === it.indicator_id}
                    onSelect={() => setSelected(it.indicator_id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* 行业：按行业分组块图 + 详情 */}
      {!loading && items.length > 0 && isIndustry && (
        <div className="mt-8 space-y-10">
          {groups.map((g) => (
            <section key={g.key}>
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="font-[family-name:var(--font-display)] text-lg tracking-tight text-[var(--ink)]">
                  {g.label}
                </h2>
                <span className="text-xs tabular-nums text-[var(--muted)]">{g.rows.length} 项</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {g.rows.map((it) => (
                  <IndicatorBlock
                    key={it.indicator_id}
                    item={it}
                    active={active?.indicator_id === it.indicator_id}
                    onSelect={() => setSelected(it.indicator_id)}
                  />
                ))}
              </div>
            </section>
          ))}
          {active && industry !== "" && (
            <div className="lg:max-w-md">
              <DetailPanel active={active} />
            </div>
          )}
        </div>
      )}

      {/* 全球 / 中国：块图 + 详情 */}
      {!loading && items.length > 0 && !isAll && !isIndustry && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
          <div className="grid gap-3 sm:grid-cols-2">
            {items.map((it) => (
              <IndicatorBlock
                key={it.indicator_id}
                item={it}
                active={active?.indicator_id === it.indicator_id}
                onSelect={() => setSelected(it.indicator_id)}
              />
            ))}
          </div>
          {active && <DetailPanel active={active} />}
        </div>
      )}
    </div>
  );
}
