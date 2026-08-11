"use client";

import { formatBodyBlocks } from "@/lib/formatBody";

interface ItemBodyProps {
  body: string;
  className?: string;
}

/** 网页/资讯正文：分段、引用与短行数据块的阅读排版 */
export function ItemBody({ body, className = "" }: ItemBodyProps) {
  const blocks = formatBodyBlocks(body);
  if (!blocks.length) return null;

  return (
    <div className={`prose-article ${className}`.trim()}>
      {blocks.map((b, i) => {
        if (b.type === "quote") {
          return (
            <blockquote key={i} className="prose-article-quote">
              <p>{b.text}</p>
              {b.cite ? <cite>{b.cite}</cite> : null}
            </blockquote>
          );
        }
        if (b.type === "lines") {
          return (
            <div key={i} className="prose-article-lines">
              {b.lines.map((line, j) => (
                <p key={j}>{line}</p>
              ))}
            </div>
          );
        }
        return (
          <p key={i} className="prose-article-p">
            {b.text}
          </p>
        );
      })}
    </div>
  );
}
