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
  content_type?: string;
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

export type FeedSource = {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  config?: Record<string, unknown>;
};

export type DigestVaultSource = {
  id: string;
  label: string;
  path: string;
  enabled: boolean;
  readable: boolean;
};

export type DigestVaultStatus = {
  status: string;
  readable: boolean;
  config_file: string;
  message: string;
  sources: DigestVaultSource[];
};

export type DigestVaultFile = {
  source_id: string;
  source_label: string;
  name: string;
  path: string;
  mtime: string;
  size: number;
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
    let detail = "";
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail != null) detail = JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `${res.status} ${path}`);
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
    req<{
      date: string;
      markdown: string | null;
      html?: string | null;
      highlights: string[];
      source?: string | null;
      run_id?: string | null;
      vault?: { source?: string; source_label?: string; path?: string; mtime?: string } | null;
      empty: boolean;
    }>("/digests/today"),
  digestVaultStatus: () => req<DigestVaultStatus>("/digests/vault/status"),
  digestVaultFiles: (opts?: { source?: string; limit?: number; q?: string }) => {
    const sp = new URLSearchParams();
    if (opts?.source) sp.set("source", opts.source);
    if (opts?.limit) sp.set("limit", String(opts.limit));
    if (opts?.q) sp.set("q", opts.q);
    const qs = sp.toString();
    return req<{ files: DigestVaultFile[]; count: number }>(
      `/digests/vault/files${qs ? `?${qs}` : ""}`
    );
  },
  digestVaultFile: (source: string, path: string) =>
    req<{
      source_id: string;
      source_label: string;
      name: string;
      path: string;
      mtime: string;
      size: number;
      html: string;
    }>(
      `/digests/vault/file?source=${encodeURIComponent(source)}&path=${encodeURIComponent(path)}`
    ),
  recommendations: () =>
    req<{ as_of: string; items: { score: number; reason: string; item: Item }[] }>(
      "/recommendations"
    ),
  sources: () => req<{ sources: FeedSource[] }>("/sources"),
  createSource: (body: {
    name: string;
    type: string;
    config?: Record<string, unknown>;
    enabled?: boolean;
  }) =>
    req<FeedSource>("/sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSource: (
    id: string,
    body: { enabled?: boolean; name?: string; config?: Record<string, unknown> }
  ) =>
    req<FeedSource>(`/sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  toggleSource: (id: string, enabled: boolean) =>
    req<FeedSource>(`/sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  deleteSource: (id: string) =>
    req<{ id: string; deleted: boolean }>(`/sources/${id}`, { method: "DELETE" }),
  upsertVaultSource: (body: { id: string; label: string; path: string; enabled?: boolean }) =>
    req<DigestVaultSource>("/digests/vault/sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  toggleVaultSource: (id: string, enabled: boolean) =>
    req<DigestVaultSource>(`/digests/vault/sources/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  deleteVaultSource: (id: string) =>
    req<{ id: string; deleted: boolean }>(
      `/digests/vault/sources/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
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
