"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "今日" },
  { href: "/digest", label: "日报" },
  { href: "/feed", label: "浏览" },
  { href: "/saved", label: "收藏" },
  { href: "/notes", label: "笔记" },
  { href: "/subscribe", label: "订阅" },
  { href: "/settings", label: "设置" },
];

export function BottomNav() {
  const path = usePathname();
  return (
    <nav className="fixed bottom-0 inset-x-0 z-40 border-t border-[var(--line)] bg-[var(--bg)]/95 backdrop-blur md:hidden">
      <ul className="grid grid-cols-7 text-[11px] sm:text-sm">
        {tabs.map((t) => {
          const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                className={`flex items-center justify-center py-3 transition-colors ${
                  active ? "text-[var(--accent)] font-medium" : "text-[var(--muted)]"
                }`}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function SideNav() {
  const path = usePathname();
  return (
    <aside className="hidden md:flex md:w-48 md:flex-col md:gap-1 md:pt-8 md:pr-6">
      <div className="mb-6 font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--ink)]">
        NewsC
      </div>
      {tabs.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`rounded-md px-3 py-2 text-sm transition-colors ${
              active
                ? "bg-[var(--surface)] text-[var(--ink)] font-medium"
                : "text-[var(--muted)] hover:text-[var(--ink)]"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </aside>
  );
}
