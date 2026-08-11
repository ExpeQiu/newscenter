"use client";

import { useEffect, useState } from "react";
import { api, type Item } from "@/lib/api";
import { ItemCard } from "@/components/ItemCard";

export default function SavedPage() {
  const [items, setItems] = useState<Item[]>([]);

  useEffect(() => {
    api.items("?starred=true&limit=50").then((d) => setItems(d.items)).catch(console.error);
  }, []);

  return (
    <div className="animate-fade-up">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">收藏</h1>
      <p className="mt-2 text-sm text-[var(--muted)]">星标内容集中在此。</p>
      <div className="mt-4">
        {items.map((item) => (
          <ItemCard
            key={item.id}
            item={item}
            onChange={(next) => setItems((prev) => prev.map((x) => (x.id === next.id ? next : x)))}
          />
        ))}
        {items.length === 0 ? <p className="mt-8 text-sm text-[var(--muted)]">还没有星标。</p> : null}
      </div>
    </div>
  );
}
