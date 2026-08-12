"use client";

import { useEffect, useMemo, useRef } from "react";
import { API_BASE } from "@/lib/api";

interface HtmlPreviewProps {
  /** iframe 直接加载的 HTML 文档 URL（优先） */
  src?: string | null;
  /** 兼容：无 src 时用 srcDoc */
  content?: string | null;
  title?: string;
}

/** 沙箱 iframe 按完整 HTML 文档渲染（禁脚本），对齐 AgentCenter 输出物预览 */
export function HtmlPreview({ src, content, title }: HtmlPreviewProps) {
  if (!src && !content) return null;
  return (
    <iframe
      title={title || "HTML 日报"}
      src={src || undefined}
      srcDoc={src ? undefined : content || undefined}
      sandbox=""
      className="block min-h-[78vh] w-full rounded-md border border-[var(--line)] bg-white"
      referrerPolicy="no-referrer"
    />
  );
}

/** 轻量去脚本，供页内划选（iframe 内无法右键入库） */
export function stripActiveHtml(html: string): string {
  if (!html) return "";
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<iframe\b[^>]*>[\s\S]*?<\/iframe>/gi, "")
    .replace(/\son[a-z]+\s*=\s*(['"]).*?\1/gi, "")
    .replace(/\s(href|src)\s*=\s*(['"])\s*javascript:[^'"]*\2/gi, "");
}

function extractBodyInner(html: string): string {
  const m = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  return (m ? m[1] : html).trim();
}

function extractStyleBlocks(html: string): string[] {
  const out: string[] = [];
  const re = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) != null) {
    if (m[1]?.trim()) out.push(m[1]);
  }
  return out;
}

/** 将文档级 html/body 选择器改写到 Shadow 内根节点，保留原 HTML 排版 */
function scopeDocumentCss(css: string, scope: string): string {
  return css
    .replace(/(^|[,{}\s>+~])html\b/gi, `$1${scope}`)
    .replace(/(^|[,{}\s>+~])body\b/gi, `$1${scope}`);
}

const DIGEST_SCOPE = ".digest-html-root";

/** 页内渲染 HTML：Shadow DOM 保留原 <style>，并支持划选加入笔记 */
export function SelectableDigestHtml({
  html,
  title,
  className = "",
}: {
  html: string;
  title?: string;
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const payload = useMemo(() => {
    const cleaned = stripActiveHtml(html);
    const styles = extractStyleBlocks(html)
      .map((css) => scopeDocumentCss(css, DIGEST_SCOPE))
      .join("\n");
    const body = extractBodyInner(cleaned);
    return { styles, body };
  }, [html]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const shadow = host.shadowRoot ?? host.attachShadow({ mode: "open" });
    if (!payload.body) {
      shadow.innerHTML = "";
      return;
    }
    shadow.innerHTML = `
<style>
  :host { display: block; background: #fff; color: #333; }
  ${payload.styles}
</style>
<div class="digest-html-root">${payload.body}</div>`;
    console.info(
      "[digest] selectable_html styles=%d body_chars=%d title=%s",
      payload.styles.length,
      payload.body.length,
      title || ""
    );
  }, [payload, title]);

  if (!payload.body) return null;
  return (
    <div
      ref={hostRef}
      title={title}
      className={`min-h-[12rem] rounded-md border border-[var(--line)] bg-white ${className}`.trim()}
    />
  );
}

export function digestVaultRawUrl(source: string, path: string): string {
  return `${API_BASE}/digests/vault/raw?source=${encodeURIComponent(source)}&path=${encodeURIComponent(path)}`;
}
