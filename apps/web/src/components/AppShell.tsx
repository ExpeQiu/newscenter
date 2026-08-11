"use client";

import { BottomNav, SideNav } from "@/components/Nav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="mx-auto flex min-h-screen max-w-[90rem] gap-2 px-4 pb-24 pt-6 md:pb-10 md:pt-8">
        <SideNav />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <BottomNav />
    </>
  );
}
