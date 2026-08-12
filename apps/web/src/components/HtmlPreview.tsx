"use client";

import { useMemo } from "react";
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

/** 页内渲染 HTML，支持划选加入笔记 */
export function SelectableDigestHtml({
  html,
  title,
  className = "",
}: {
  html: string;
  title?: string;
  className?: string;
}) {
  const safe = useMemo(() => extractBodyInner(stripActiveHtml(html)), [html]);
  if (!safe) return null;
  return (
    <article
      title={title}
      className={`prose-digest min-h-[12rem] rounded-md border border-[var(--line)] bg-white px-4 py-5 text-[15px] leading-relaxed text-[var(--body)] ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: safe }}
    />
  );
}

export function digestVaultRawUrl(source: string, path: string): string {
  return `${API_BASE}/digests/vault/raw?source=${encodeURIComponent(source)}&path=${encodeURIComponent(path)}`;
}
