/** 云端设 NEXT_PUBLIC_API_BASE=/api（经 Next rewrite）；本机默认直连 orchestrator */
function resolveApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE;
  if (raw === undefined) return "http://127.0.0.1:8787";
  if (raw === "") return "/api";
  return raw.replace(/\/$/, "");
}

const API_BASE = resolveApiBase();

export type Marks = {
  is_read: boolean;
  is_starred: boolean;
  is_archived: boolean;
  note?: string | null;
};

export type ItemMeta = {
  play?: number | string | null;
  duration?: string | null;
  author?: string | null;
  comment?: number | string | null;
  danmaku?: number | string | null;
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
  meta?: ItemMeta;
  marks: Marks;
  tags: { name: string; origin: string }[];
};

export type FeedSource = {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  config?: Record<string, unknown>;
  identity_changed?: boolean;
  purged_items?: number;
  resync?: { inserted?: number; skipped?: number; total?: number; run_id?: string };
  resync_error?: string;
};

export type DigestVaultSource = {
  id: string;
  label: string;
  path: string;
  enabled: boolean;
  readable: boolean;
  refresh_interval?: string;
  refresh_label?: string;
  tags?: string[];
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

export type NoteColumn = {
  id: string;
  name: string;
  sort_order: number;
  created_at?: string | null;
  note_count?: number;
};

export type Note = {
  id: string;
  column_id: string;
  quote_text: string;
  source_kind: "item" | "digest";
  item_id?: string | null;
  digest_date?: string | null;
  source_title: string;
  source_url?: string | null;
  created_at?: string | null;
};

export type InsightEvent = {
  id: string;
  occurred_at?: string | null;
  dimension: string;
  industry?: string | null;
  entity?: string | null;
  title: string;
  summary: string;
  source_urls: string[];
  query_id?: string | null;
  created_at?: string | null;
};

export type MacroSnapshotItem = {
  indicator_id: string;
  label: string;
  scope: string;
  industry?: string | null;
  unit: string;
  description?: string | null;
  latest?: {
    id: string;
    indicator_id: string;
    observed_at?: string | null;
    value?: number | null;
    value_text?: string | null;
    period_label: string;
    source_urls: string[];
  } | null;
  history: {
    id: string;
    observed_at?: string | null;
    value?: number | null;
    value_text?: string | null;
    period_label: string;
  }[];
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
      vault?: {
        source?: string;
        source_label?: string;
        path?: string;
        mtime?: string;
        count?: number;
      } | null;
      synthesized?: boolean;
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
    req<{
      as_of: string;
      items: { score: number; reason: string; item: Item }[];
      fallback?: boolean;
    }>("/recommendations"),
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
  upsertVaultSource: (body: {
    id: string;
    label: string;
    path: string;
    enabled?: boolean;
    refresh_interval?: string;
    tags?: string[];
  }) =>
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
  cloudSyncConfig: () =>
    req<{
      configured: boolean;
      config_path: string;
      deploy_host: string;
      deploy_dir: string;
      tunnel_local_port: number;
      cloud_database_url: string;
      cloud_database_url_set: boolean;
      local_database_url: string;
      tunnel_up: boolean | null;
      push_schedule_enabled: boolean;
      push_schedule_mode: "daily" | "interval";
      push_schedule_times: string[];
      push_schedule_interval_hours: number;
      push_schedule_installed: boolean;
      last_push: {
        log_path: string;
        exists: boolean;
        mtime?: number;
        tail: string[];
      };
    }>("/cloud-sync/config"),
  saveCloudSyncConfig: (body: {
    deploy_host: string;
    deploy_dir: string;
    tunnel_local_port: number;
    cloud_database_url: string;
    local_database_url: string;
    push_schedule_enabled: boolean;
    push_schedule_mode: "daily" | "interval";
    push_schedule_times: string[];
    push_schedule_interval_hours: number;
    apply_schedule?: boolean;
  }) =>
    req("/cloud-sync/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  ensureCloudTunnel: () =>
    req<{
      ok: boolean;
      returncode: number;
      output: string;
      tunnel_up: boolean | null;
    }>("/cloud-sync/tunnel", { method: "POST" }),
  pushDbToCloud: (dry_run = false) =>
    req<{
      ok: boolean;
      dry_run: boolean;
      returncode: number;
      output: string;
    }>("/cloud-sync/push", {
      method: "POST",
      body: JSON.stringify({ dry_run }),
    }),
  processItemAi: (itemId: string, force = false) =>
    req<{
      provider: string;
      item_id: string;
      processed: number;
      failed: number;
      summary?: string | null;
      ai_category?: string | null;
      item: Item;
    }>(`/ai/items/${encodeURIComponent(itemId)}/process`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  ask: (question: string, item_id?: string) =>
    req<{ answer: string; citations: string[] }>("/ai/ask", {
      method: "POST",
      body: JSON.stringify({ question, item_id }),
    }),
  noteColumns: () => req<{ columns: NoteColumn[]; count: number }>("/note-columns"),
  createNoteColumn: (name: string, sort_order?: number) =>
    req<NoteColumn>("/note-columns", {
      method: "POST",
      body: JSON.stringify({ name, sort_order }),
    }),
  patchNoteColumn: (id: string, body: { name?: string; sort_order?: number }) =>
    req<NoteColumn>(`/note-columns/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteNoteColumn: (id: string) =>
    req<{ id: string; deleted: boolean; notes_removed?: number }>(
      `/note-columns/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  notes: (opts?: { column_id?: string; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams();
    if (opts?.column_id) sp.set("column_id", opts.column_id);
    if (opts?.limit) sp.set("limit", String(opts.limit));
    if (opts?.offset) sp.set("offset", String(opts.offset));
    const qs = sp.toString();
    return req<{ notes: Note[]; count: number }>(`/notes${qs ? `?${qs}` : ""}`);
  },
  createNote: (body: {
    column_id: string;
    quote_text: string;
    source_kind: "item" | "digest";
    item_id?: string | null;
    digest_date?: string | null;
    source_title?: string;
    source_url?: string | null;
  }) =>
    req<Note>("/notes", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteNote: (id: string) =>
    req<{ id: string; deleted: boolean }>(`/notes/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  events: (opts?: {
    dimension?: string;
    industry?: string;
    entity?: string;
    limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (opts?.dimension) sp.set("dimension", opts.dimension);
    if (opts?.industry) sp.set("industry", opts.industry);
    if (opts?.entity) sp.set("entity", opts.entity);
    if (opts?.limit) sp.set("limit", String(opts.limit));
    const qs = sp.toString();
    return req<{ events: InsightEvent[]; count: number }>(`/events${qs ? `?${qs}` : ""}`);
  },
  event: (id: string) => req<InsightEvent>(`/events/${encodeURIComponent(id)}`),
  macroSnapshot: (opts?: { scope?: string; industry?: string }) => {
    const sp = new URLSearchParams();
    if (opts?.scope) sp.set("scope", opts.scope);
    if (opts?.industry) sp.set("industry", opts.industry);
    const qs = sp.toString();
    return req<{ items: MacroSnapshotItem[]; count: number }>(
      `/macro/snapshot${qs ? `?${qs}` : ""}`
    );
  },
  runInsight: (opts?: { force?: boolean; kind?: "all" | "event" | "macro" }) => {
    const sp = new URLSearchParams();
    if (opts?.force) sp.set("force", "true");
    if (opts?.kind) sp.set("kind", opts.kind);
    const qs = sp.toString();
    return req(`/pipelines/insight/run${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
};

export { API_BASE };
