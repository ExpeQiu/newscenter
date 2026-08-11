const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8787";

export type Marks = {
  is_read: boolean;
  is_starred: boolean;
  is_archived: boolean;
  note?: string | null;
};

export type Item = {
  id: string;
  source_type: string;
  url?: string | null;
  title: string;
  body: string;
  summary?: string | null;
  embed_provider?: string | null;
  embed_id?: string | null;
  embed_url?: string | null;
  thumbnail_url?: string | null;
  ai_category?: string | null;
  category_locked?: boolean;
  published_at?: string | null;
  fetched_at?: string | null;
  marks: Marks;
  tags: { name: string; origin: string }[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; ai_provider: string }>("/health"),
  items: (q = "") => req<{ items: Item[]; count: number }>(`/items${q}`),
  item: (id: string) => req<Item>(`/items/${id}`),
  patchMarks: (id: string, body: Partial<Marks>) =>
    req<Item>(`/items/${id}/marks`, { method: "PATCH", body: JSON.stringify(body) }),
  patchCategory: (id: string, category: string, lock = true) =>
    req<Item>(`/items/${id}/category`, {
      method: "PATCH",
      body: JSON.stringify({ category, lock }),
    }),
  digestToday: () =>
    req<{ date: string; markdown: string | null; highlights: string[]; empty: boolean }>(
      "/digests/today"
    ),
  recommendations: () =>
    req<{ as_of: string; items: { score: number; reason: string; item: Item }[] }>(
      "/recommendations"
    ),
  sources: () =>
    req<{ sources: { id: string; name: string; type: string; enabled: boolean }[] }>("/sources"),
  toggleSource: (id: string, enabled: boolean) =>
    req(`/sources/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  runPipeline: (id: string) => req(`/pipelines/${id}/run`, { method: "POST" }),
  processAi: () =>
    req("/ai/jobs/process", {
      method: "POST",
      body: JSON.stringify({ limit: 50, include_digest: true }),
    }),
  ask: (question: string, item_id?: string) =>
    req<{ answer: string; citations: string[] }>("/ai/ask", {
      method: "POST",
      body: JSON.stringify({ question, item_id }),
    }),
};

export { API_BASE };
