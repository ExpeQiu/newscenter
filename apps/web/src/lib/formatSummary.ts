/** 摘要展示：剥离模型误存的 JSON 外壳，并按句拆成可读段落 */

export function unwrapSummary(raw: string): string {
  let t = (raw || "").trim();
  if (!t) return "";

  t = t.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();

  if (t.startsWith("{") && /"summary"\s*:/.test(t)) {
    try {
      const data = JSON.parse(t) as { summary?: unknown };
      if (typeof data.summary === "string" && data.summary.trim()) {
        return data.summary.trim();
      }
    } catch {
      const m = /"summary"\s*:\s*"/.exec(t);
      if (m && m.index != null) {
        const start = m.index + m[0].length;
        const close = t.lastIndexOf("}");
        const end = close > start ? t.lastIndexOf('"', close) : t.lastIndexOf('"');
        if (end > start) {
          const extracted = t.slice(start, end).replace(/\\"/g, '"').replace(/\\n/g, "\n").trim();
          if (extracted) return extracted;
        }
      }
    }
  }

  // 去掉模型偶发的 【摘要】前缀
  return t.replace(/^【摘要】\s*/, "").trim();
}

/** 长摘要按句号拆成 1–3 句一段，便于扫读 */
export function splitSummaryParagraphs(raw: string): string[] {
  const text = unwrapSummary(raw);
  if (!text) return [];

  if (/\n/.test(text)) {
    return text
      .split(/\n+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  const sentences = text
    .split(/(?<=[。！？；])\s*/)
    .map((s) => s.trim())
    .filter(Boolean);

  if (sentences.length <= 2) return [text];

  const paras: string[] = [];
  const group = sentences.length >= 6 ? 2 : sentences.length >= 4 ? 2 : 1;
  for (let i = 0; i < sentences.length; i += group) {
    paras.push(sentences.slice(i, i + group).join(""));
  }
  return paras;
}
