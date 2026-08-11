"use client";

import { splitSummaryParagraphs } from "@/lib/formatSummary";

interface ItemSummaryProps {
  summary: string;
  emptyHint?: string;
}

/** 条目摘要：去 JSON 外壳、分句排版 */
export function ItemSummary({
  summary,
  emptyHint = "摘要尚未生成。点「AI 生成」为本条跑摘要与分类。",
}: ItemSummaryProps) {
  const paras = splitSummaryParagraphs(summary);
  if (!paras.length) {
    return <p className="prose-summary-empty">{emptyHint}</p>;
  }

  return (
    <div className="prose-summary">
      {paras.map((p, i) => (
        <p key={i} className={i === 0 ? "prose-summary-lead" : undefined}>
          {p}
        </p>
      ))}
    </div>
  );
}
