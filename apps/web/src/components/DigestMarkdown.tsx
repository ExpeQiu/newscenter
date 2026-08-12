"use client";

import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

const components: Components = {
  h1: ({ children }) => (
    <h1 className="font-[family-name:var(--font-display)] text-2xl text-[var(--ink)] md:text-[1.65rem]">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="font-[family-name:var(--font-display)] text-xl text-[var(--ink)]">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="font-[family-name:var(--font-display)] text-lg text-[var(--ink)]">{children}</h3>
  ),
  p: ({ children }) => <p className="text-[var(--body)]">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-[var(--ink)]">{children}</strong>,
  em: ({ children }) => <em className="italic text-[var(--body)]">{children}</em>,
  ul: ({ children }) => <ul className="list-disc space-y-2 pl-5 text-[var(--body)]">{children}</ul>,
  ol: ({ children }) => (
    <ol className="list-decimal space-y-2.5 pl-5 text-[var(--body)] marker:font-medium marker:text-[var(--accent)]">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1 leading-relaxed">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      className="text-[var(--accent)] underline underline-offset-2 hover:opacity-80"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[var(--accent)]/40 pl-3 text-[var(--muted)]">{children}</blockquote>
  ),
  hr: () => <hr className="border-[var(--line)]" />,
  code: ({ children }) => (
    <code className="rounded bg-[var(--surface)] px-1 py-0.5 text-[0.9em] text-[var(--ink)]">{children}</code>
  ),
};

interface DigestMarkdownProps {
  content: string;
  className?: string;
}

/** 去掉与页面「今日洞察」标题重复的开头 h1 / 条数说明引用 */
function stripRedundantLead(md: string): string {
  let s = md.trim();
  // # 今日洞察 · 2026-08-12
  s = s.replace(/^#\s*今日洞察[^\n]*\n+/u, "");
  // > 近 24 小时共 **2** 条…
  s = s.replace(/^>\s*[^\n]*(?:高度总结|条)[^\n]*\n+/u, "");
  return s.trim();
}

/** 今日洞察等 Markdown 正文：标题层级、加粗、列表可读渲染 */
export function DigestMarkdown({ content, className = "" }: DigestMarkdownProps) {
  const body = stripRedundantLead(content);
  return (
    <article className={`prose-digest ${className}`.trim()}>
      <ReactMarkdown components={components}>{body}</ReactMarkdown>
    </article>
  );
}
