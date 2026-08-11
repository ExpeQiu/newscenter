/** 将采集正文（纯文本或残留 HTML）整理为可读块，并过滤侧栏/页脚噪音 */

export type BodyBlock =
  | { type: "p"; text: string }
  | { type: "quote"; text: string; cite?: string }
  | { type: "lines"; lines: string[] };

const TAG_RE = /<\/?[a-z][\s\S]*?>/i;
const QUOTE_CITE_RE = /^(.*?)(?:\n|\s)*[—－-]{2,}\s*(.+)$/s;

/** 正文结束：页脚 / 站点导航 / 推荐区 */
const BOILERPLATE_CUT_RE =
  /(?:免责声明|法律声明|风险提示|版权所有|Copyright\s+\w|关于同花顺|软件下载|友情链接|投资者关系|联系我们|招聘英才|网友意见箱|回顶部|扫码关注|下载APP|立即下载|开通会员|相关推荐|热门推荐|猜你喜欢|责任编辑[:：])/i;

const NOISE_LINE_RE =
  /^(?:[|｜]+|更多>?|查看.+>|登录|注册|首页|资讯|行情|数据|代码|简称|事项|原因|成交价格|成交额|买卖营业部|停牌|重要公告|大宗交易|今日停复牌|溢价率|收盘总结|全球市场|热点资讯|投资机会|公司资讯|-->|Copyright\.?$|浙江同花顺.+)$/i;

function stripHtml(raw: string): string {
  let s = raw;
  s = s.replace(/<(script|style|noscript)[^>]*>[\s\S]*?<\/\1>/gi, " ");
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<\/p>/gi, "\n\n");
  s = s.replace(/<\/(div|h[1-6]|li|tr|section|article|dd|dt)>/gi, "\n");
  s = s.replace(/<[^>]+>/g, " ");
  s = s
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
    .replace(/&mdash;/gi, "—")
    .replace(/&ldquo;/gi, "“")
    .replace(/&rdquo;/gi, "”");
  return s;
}

/** 去掉广告/侧栏/页脚残留行，截断页脚之后内容 */
export function cleanArticleText(raw: string): string {
  let s = TAG_RE.test(raw) ? stripHtml(raw) : raw;
  s = s.replace(/\r\n?/g, "\n").replace(/\u00a0/g, " ");
  s = s.replace(/[ \t\f\v]+/g, " ");
  s = s.replace(/ *\n */g, "\n");
  s = s.replace(/\n{3,}/g, "\n\n").trim();
  if (!s) return "";

  const cut = BOILERPLATE_CUT_RE.exec(s);
  if (cut && cut.index != null && cut.index > 200) {
    s = s.slice(0, cut.index).trim();
  }

  const lines: string[] = [];
  for (const ln of s.split("\n")) {
    const t = ln.trim();
    if (!t) {
      if (lines.length && lines[lines.length - 1] !== "") lines.push("");
      continue;
    }
    if (NOISE_LINE_RE.test(t)) continue;
    if (t.length <= 2 && ["|", "｜", "·", "-", "—"].includes(t)) continue;
    // 侧栏表格残片：连续短词行（如股票简称列表）在后半段过密时跳过
    lines.push(t);
  }

  const out: string[] = [];
  for (const ln of lines) {
    if (ln === "" && (!out.length || out[out.length - 1] === "")) continue;
    out.push(ln);
  }

  // 后半段若出现大量极短行（侧栏表格），从该处截断
  const nonEmpty = out.filter((l) => l !== "");
  if (nonEmpty.length > 40) {
    let shortRun = 0;
    let cutAt = -1;
    let seen = 0;
    for (let i = 0; i < out.length; i++) {
      const t = out[i];
      if (!t) continue; // 空行不打断短行串（侧栏表常隔行）
      seen += 1;
      if (seen < Math.floor(nonEmpty.length * 0.4)) continue;
      if (t.length <= 10) {
        shortRun += 1;
        if (shortRun >= 6) {
          cutAt = i - shortRun + 1;
          // 回退到本轮短行串起点在 out 中的真实下标
          let back = 0;
          let j = i;
          while (j >= 0 && back < shortRun) {
            if (out[j]) back += 1;
            if (back >= shortRun) {
              cutAt = j;
              break;
            }
            j -= 1;
          }
          break;
        }
      } else {
        shortRun = 0;
      }
    }
    if (cutAt > 20) {
      return out.slice(0, cutAt).join("\n").trim();
    }
  }

  return out.join("\n").trim();
}

function normalize(raw: string): string {
  return cleanArticleText(raw);
}

function looksLikeDataBlock(lines: string[]): boolean {
  if (lines.length < 2) return false;
  const short = lines.filter((l) => l.length <= 48).length;
  return short / lines.length >= 0.6;
}

function toQuote(text: string): BodyBlock | null {
  const t = text.trim();
  if (t.length < 8) return null;
  const m = QUOTE_CITE_RE.exec(t);
  if (m && m[1].trim().length >= 6) {
    return { type: "quote", text: m[1].trim(), cite: m[2].trim() };
  }
  if (
    (t.startsWith("“") || t.startsWith('"') || t.startsWith("「")) &&
    /[—－-]{2,}/.test(t)
  ) {
    const parts = t.split(/[—－-]{2,}/);
    if (parts.length >= 2) {
      return { type: "quote", text: parts[0].trim(), cite: parts.slice(1).join("—").trim() };
    }
  }
  return null;
}

/** 将 item.body 拆成段落 / 引用 / 短行数据块 */
export function formatBodyBlocks(raw: string): BodyBlock[] {
  const text = normalize(raw);
  if (!text) return [];

  const chunks = text.split(/\n\n+/).flatMap((chunk) => {
    const lines = chunk
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) return [] as string[];
    if (looksLikeDataBlock(lines)) return [lines.join("\n")];
    // 长文常见单换行分段
    if (lines.length > 1 && lines.every((l) => l.length > 40)) {
      return lines;
    }
    return [lines.join("\n")];
  });

  const blocks: BodyBlock[] = [];
  for (const chunk of chunks) {
    const lines = chunk
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) continue;

    if (lines.length > 1 && looksLikeDataBlock(lines)) {
      blocks.push({ type: "lines", lines });
      continue;
    }

    const joined = lines.join("\n");
    const quote = toQuote(joined);
    if (quote) {
      blocks.push(quote);
      continue;
    }

    blocks.push({ type: "p", text: joined.replace(/\n/g, "") });
  }
  return blocks;
}
