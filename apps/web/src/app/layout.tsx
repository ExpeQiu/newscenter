import type { Metadata } from "next";
import "./globals.css";
import { BottomNav, SideNav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "NewsC · 每日一站",
  description: "个人化内容聚合：摘要先行，洞察全网",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <div className="mx-auto flex min-h-screen max-w-5xl gap-2 px-4 pb-24 pt-6 md:pb-10 md:pt-8">
          <SideNav />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
        <BottomNav />
      </body>
    </html>
  );
}
