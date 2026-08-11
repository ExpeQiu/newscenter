"use client";

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

export function digestVaultRawUrl(source: string, path: string): string {
  return `${API_BASE}/digests/vault/raw?source=${encodeURIComponent(source)}&path=${encodeURIComponent(path)}`;
}
