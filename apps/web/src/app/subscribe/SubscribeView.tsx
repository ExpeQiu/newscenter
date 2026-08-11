"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  api,
  type DigestVaultSource,
  type DigestVaultStatus,
  type FeedSource,
} from "@/lib/api";

const SOCIAL_PLATFORMS = [
  { v: "weibo", l: "微博" },
  { v: "x", l: "X / Twitter" },
  { v: "xiaohongshu", l: "小红书" },
  { v: "other", l: "其他" },
];

const SECTIONS = [
  { id: "sec-digest", label: "日报路径" },
  { id: "sec-web", label: "网页 / RSS" },
  { id: "sec-social", label: "社媒" },
  { id: "sec-video", label: "B站 / YouTube" },
] as const;

function cfgStr(cfg: Record<string, unknown> | undefined, key: string): string {
  const v = cfg?.[key];
  return typeof v === "string" ? v : v != null ? String(v) : "";
}

function platformLabel(v: string): string {
  return SOCIAL_PLATFORMS.find((p) => p.v === v)?.l || v || "social";
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]";

function SourceRow({
  title,
  meta,
  enabled,
  onEdit,
  onToggle,
  onDelete,
}: {
  title: string;
  meta: string;
  enabled: boolean;
  onEdit?: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-[var(--ink)]">{title}</span>
          <span
            className={`text-xs ${enabled ? "text-[var(--accent)]" : "text-[var(--muted)]"}`}
          >
            {enabled ? "启用中" : "已停用"}
          </span>
        </div>
        <div className="mt-0.5 break-all text-[var(--muted)]">{meta}</div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {onEdit ? (
          <button
            type="button"
            className="rounded-md border border-[var(--line)] px-3 py-1"
            onClick={onEdit}
          >
            编辑
          </button>
        ) : null}
        <button
          type="button"
          className="rounded-md border border-[var(--line)] px-3 py-1"
          onClick={onToggle}
        >
          {enabled ? "停用" : "启用"}
        </button>
        <button
          type="button"
          className="rounded-md border border-[var(--line)] px-3 py-1 text-[var(--muted)] hover:text-[var(--ink)]"
          onClick={onDelete}
        >
          删除
        </button>
      </div>
    </li>
  );
}

export default function SubscribePage() {
  const [vault, setVault] = useState<DigestVaultStatus | null>(null);
  const [sources, setSources] = useState<FeedSource[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState("");

  const [digestForm, setDigestForm] = useState({
    id: "",
    label: "",
    path: "",
    editing: false,
  });
  const [webForm, setWebForm] = useState({
    id: "" as string | null,
    name: "",
    url: "",
    kind: "web" as "web" | "rss",
  });
  const [socialForm, setSocialForm] = useState({
    id: "" as string | null,
    name: "",
    platform: "weibo",
    handle: "",
  });
  const [videoForm, setVideoForm] = useState({
    id: "" as string | null,
    name: "",
    type: "bilibili" as "bilibili" | "youtube",
    account: "",
  });

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const [v, s] = await Promise.all([api.digestVaultStatus(), api.sources()]);
      setVault(v);
      setSources(s.sources);
      console.info(
        "[subscribe] refresh vault=%d feed=%d",
        v.sources.length,
        s.sources.length
      );
    } catch (e) {
      console.error("[subscribe] refresh failed", e);
      setErr(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const webSources = useMemo(
    () => sources.filter((s) => s.type === "web" || s.type === "rss"),
    [sources]
  );
  const socialSources = useMemo(() => sources.filter((s) => s.type === "social"), [sources]);
  const videoSources = useMemo(
    () => sources.filter((s) => s.type === "bilibili" || s.type === "youtube"),
    [sources]
  );

  const counts = {
    digest: vault?.sources.length ?? 0,
    web: webSources.length,
    social: socialSources.length,
    video: videoSources.length,
  };

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setLog(`${label}…`);
    setErr(null);
    try {
      await fn();
      setLog(`${label} 完成`);
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[subscribe]", label, e);
      setLog(`${label} 失败：${msg}`);
      setErr(msg);
    } finally {
      setBusy(false);
    }
  }

  function resetDigestForm() {
    setDigestForm({ id: "", label: "", path: "", editing: false });
  }

  function editVault(s: DigestVaultSource) {
    setDigestForm({
      id: s.id,
      label: s.label,
      path: s.path,
      editing: true,
    });
    document.getElementById("sec-digest")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function editWeb(s: FeedSource) {
    setWebForm({
      id: s.id,
      name: s.name,
      url: cfgStr(s.config, "url"),
      kind: s.type === "rss" ? "rss" : "web",
    });
    document.getElementById("sec-web")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function editSocial(s: FeedSource) {
    setSocialForm({
      id: s.id,
      name: s.name,
      platform: cfgStr(s.config, "platform") || "other",
      handle: cfgStr(s.config, "handle"),
    });
    document.getElementById("sec-social")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function editVideo(s: FeedSource) {
    setVideoForm({
      id: s.id,
      name: s.name,
      type: s.type === "youtube" ? "youtube" : "bilibili",
      account: cfgStr(s.config, "account"),
    });
    document.getElementById("sec-video")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function onDigestSubmit(e: FormEvent) {
    e.preventDefault();
    const id = digestForm.id.trim();
    const path = digestForm.path.trim();
    if (!id || !path) return;
    void run(digestForm.editing ? "更新日报路径" : "添加日报路径", async () => {
      await api.upsertVaultSource({
        id,
        label: digestForm.label.trim() || id,
        path,
        enabled: true,
      });
      resetDigestForm();
    });
  }

  function onWebSubmit(e: FormEvent) {
    e.preventDefault();
    const name = webForm.name.trim();
    const url = webForm.url.trim();
    if (!name || !url) return;
    void run(webForm.id ? "更新网页信源" : "添加网页信源", async () => {
      if (webForm.id) {
        await api.updateSource(webForm.id, {
          name,
          config: { url },
        });
      } else {
        await api.createSource({
          name,
          type: webForm.kind,
          config: { url },
        });
      }
      setWebForm({ id: null, name: "", url: "", kind: "web" });
    });
  }

  function onSocialSubmit(e: FormEvent) {
    e.preventDefault();
    const name = socialForm.name.trim();
    const handle = socialForm.handle.trim();
    if (!name || !handle) return;
    void run(socialForm.id ? "更新社媒账号" : "绑定社媒账号", async () => {
      const config = { platform: socialForm.platform, handle };
      if (socialForm.id) {
        await api.updateSource(socialForm.id, { name, config });
      } else {
        await api.createSource({ name, type: "social", config });
      }
      setSocialForm({ id: null, name: "", platform: "weibo", handle: "" });
    });
  }

  function onVideoSubmit(e: FormEvent) {
    e.preventDefault();
    const name = videoForm.name.trim();
    const account = videoForm.account.trim();
    if (!name || !account) return;
    void run(videoForm.id ? "更新视频账号" : "绑定视频账号", async () => {
      if (videoForm.id) {
        await api.updateSource(videoForm.id, {
          name,
          config: { account },
        });
      } else {
        await api.createSource({
          name,
          type: videoForm.type,
          config: { account },
        });
      }
      setVideoForm({ id: null, name: "", type: "bilibili", account: "" });
    });
  }

  return (
    <div className="animate-fade-up max-w-2xl space-y-10">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-3xl">订阅</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          管理信源：日报路径、网页、社媒与 B 站 / YouTube 账号。采集运维仍在{" "}
          <Link href="/settings" className="text-[var(--accent)] underline-offset-2 hover:underline">
            设置
          </Link>
          。
        </p>
        <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-[var(--muted)]">
          {SECTIONS.map((s, i) => {
            const n = [counts.digest, counts.web, counts.social, counts.video][i];
            return (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="hover:text-[var(--ink)]"
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                {s.label}
                <span className="ml-1 text-xs tabular-nums">({n})</span>
              </a>
            );
          })}
        </nav>
      </header>

      {err ? (
        <p className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--body)]">
          {err}
        </p>
      ) : null}
      {log ? <p className="text-xs text-[var(--muted)]">{log}</p> : null}

      <section id="sec-digest" className="scroll-mt-6 space-y-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">日报获取路径</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            指向本机 HTML 目录（写入 digest-sources.yml）。配置后可在{" "}
            <Link href="/digest" className="text-[var(--accent)] underline-offset-2 hover:underline">
              日报
            </Link>{" "}
            预览。
            {vault?.config_file ? (
              <span className="mt-1 block break-all text-xs">配置：{vault.config_file}</span>
            ) : null}
          </p>
        </div>
        <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {(vault?.sources ?? []).map((s: DigestVaultSource) => (
            <SourceRow
              key={s.id}
              title={s.label}
              meta={`${s.id} · ${s.path}${s.readable ? "" : " · 目录不可读"}`}
              enabled={s.enabled}
              onEdit={() => editVault(s)}
              onToggle={() =>
                void run(`${s.enabled ? "停用" : "启用"} ${s.label}`, () =>
                  api.toggleVaultSource(s.id, !s.enabled)
                )
              }
              onDelete={() => {
                if (!confirm(`删除日报来源「${s.label}」？`)) return;
                void run(`删除 ${s.label}`, () => api.deleteVaultSource(s.id));
              }}
            />
          ))}
          {(vault?.sources.length ?? 0) === 0 ? (
            <li className="py-3 text-sm text-[var(--muted)]">尚无日报路径。</li>
          ) : null}
        </ul>
        <form onSubmit={onDigestSubmit} className="grid gap-3 sm:grid-cols-2">
          <Field label="ID">
            <input
              className={inputCls}
              required
              placeholder="ai-tech"
              value={digestForm.id}
              onChange={(e) => setDigestForm((f) => ({ ...f, id: e.target.value }))}
              disabled={busy || digestForm.editing}
            />
          </Field>
          <Field label="名称">
            <input
              className={inputCls}
              placeholder="AI技术日报"
              value={digestForm.label}
              onChange={(e) => setDigestForm((f) => ({ ...f, label: e.target.value }))}
              disabled={busy}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="目录路径">
              <input
                className={inputCls}
                required
                placeholder="/path/to/html 或 daily"
                value={digestForm.path}
                onChange={(e) => setDigestForm((f) => ({ ...f, path: e.target.value }))}
                disabled={busy}
              />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            >
              {digestForm.editing ? "保存路径" : "添加路径"}
            </button>
            {digestForm.editing ? (
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
                onClick={resetDigestForm}
              >
                取消编辑
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section id="sec-web" className="scroll-mt-6 space-y-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">指定网页</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">网页 URL 或 RSS Feed，纳入采集清单。</p>
        </div>
        <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {webSources.map((s) => (
            <SourceRow
              key={s.id}
              title={s.name}
              meta={`${s.type.toUpperCase()} · ${cfgStr(s.config, "url") || "（未配置 URL）"}`}
              enabled={s.enabled}
              onEdit={() => editWeb(s)}
              onToggle={() =>
                void run(`${s.enabled ? "停用" : "启用"} ${s.name}`, () =>
                  api.toggleSource(s.id, !s.enabled)
                )
              }
              onDelete={() => {
                if (!confirm(`删除「${s.name}」？`)) return;
                void run(`删除 ${s.name}`, () => api.deleteSource(s.id));
              }}
            />
          ))}
          {webSources.length === 0 ? (
            <li className="py-3 text-sm text-[var(--muted)]">尚无网页 / RSS 信源。</li>
          ) : null}
        </ul>
        <form onSubmit={onWebSubmit} className="grid gap-3 sm:grid-cols-2">
          <Field label="名称">
            <input
              className={inputCls}
              required
              value={webForm.name}
              onChange={(e) => setWebForm((f) => ({ ...f, name: e.target.value }))}
              disabled={busy}
            />
          </Field>
          <Field label="类型">
            <select
              className={inputCls}
              value={webForm.kind}
              onChange={(e) =>
                setWebForm((f) => ({ ...f, kind: e.target.value as "web" | "rss" }))
              }
              disabled={busy || !!webForm.id}
            >
              <option value="web">网页</option>
              <option value="rss">RSS</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="URL">
              <input
                className={inputCls}
                type="url"
                required
                placeholder="https://"
                value={webForm.url}
                onChange={(e) => setWebForm((f) => ({ ...f, url: e.target.value }))}
                disabled={busy}
              />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            >
              {webForm.id ? "保存网页" : "添加网页"}
            </button>
            {webForm.id ? (
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
                onClick={() => setWebForm({ id: null, name: "", url: "", kind: "web" })}
              >
                取消编辑
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section id="sec-social" className="scroll-mt-6 space-y-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">社媒账号</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">绑定微博 / X / 小红书等账号标识。</p>
        </div>
        <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {socialSources.map((s) => (
            <SourceRow
              key={s.id}
              title={s.name}
              meta={`${platformLabel(cfgStr(s.config, "platform"))} · @${cfgStr(s.config, "handle") || "—"}`}
              enabled={s.enabled}
              onEdit={() => editSocial(s)}
              onToggle={() =>
                void run(`${s.enabled ? "停用" : "启用"} ${s.name}`, () =>
                  api.toggleSource(s.id, !s.enabled)
                )
              }
              onDelete={() => {
                if (!confirm(`删除「${s.name}」？`)) return;
                void run(`删除 ${s.name}`, () => api.deleteSource(s.id));
              }}
            />
          ))}
          {socialSources.length === 0 ? (
            <li className="py-3 text-sm text-[var(--muted)]">尚未绑定社媒账号。</li>
          ) : null}
        </ul>
        <form onSubmit={onSocialSubmit} className="grid gap-3 sm:grid-cols-2">
          <Field label="显示名">
            <input
              className={inputCls}
              required
              value={socialForm.name}
              onChange={(e) => setSocialForm((f) => ({ ...f, name: e.target.value }))}
              disabled={busy}
            />
          </Field>
          <Field label="平台">
            <select
              className={inputCls}
              value={socialForm.platform}
              onChange={(e) => setSocialForm((f) => ({ ...f, platform: e.target.value }))}
              disabled={busy}
            >
              {SOCIAL_PLATFORMS.map((p) => (
                <option key={p.v} value={p.v}>
                  {p.l}
                </option>
              ))}
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="账号 / Handle">
              <input
                className={inputCls}
                required
                placeholder="@username 或 UID"
                value={socialForm.handle}
                onChange={(e) => setSocialForm((f) => ({ ...f, handle: e.target.value }))}
                disabled={busy}
              />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            >
              {socialForm.id ? "保存账号" : "绑定账号"}
            </button>
            {socialForm.id ? (
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
                onClick={() =>
                  setSocialForm({ id: null, name: "", platform: "weibo", handle: "" })
                }
              >
                取消编辑
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section id="sec-video" className="scroll-mt-6 space-y-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">B 站 / YouTube</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">绑定 UP 主 mid 或 YouTube 频道 ID / URL。</p>
        </div>
        <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {videoSources.map((s) => (
            <SourceRow
              key={s.id}
              title={s.name}
              meta={`${s.type === "bilibili" ? "B站" : "YouTube"} · ${cfgStr(s.config, "account") || "（未配置账号）"}`}
              enabled={s.enabled}
              onEdit={() => editVideo(s)}
              onToggle={() =>
                void run(`${s.enabled ? "停用" : "启用"} ${s.name}`, () =>
                  api.toggleSource(s.id, !s.enabled)
                )
              }
              onDelete={() => {
                if (!confirm(`删除「${s.name}」？`)) return;
                void run(`删除 ${s.name}`, () => api.deleteSource(s.id));
              }}
            />
          ))}
          {videoSources.length === 0 ? (
            <li className="py-3 text-sm text-[var(--muted)]">尚未绑定视频账号。</li>
          ) : null}
        </ul>
        <form onSubmit={onVideoSubmit} className="grid gap-3 sm:grid-cols-2">
          <Field label="显示名">
            <input
              className={inputCls}
              required
              value={videoForm.name}
              onChange={(e) => setVideoForm((f) => ({ ...f, name: e.target.value }))}
              disabled={busy}
            />
          </Field>
          <Field label="平台">
            <select
              className={inputCls}
              value={videoForm.type}
              onChange={(e) =>
                setVideoForm((f) => ({
                  ...f,
                  type: e.target.value as "bilibili" | "youtube",
                }))
              }
              disabled={busy || !!videoForm.id}
            >
              <option value="bilibili">B 站</option>
              <option value="youtube">YouTube</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label={videoForm.type === "bilibili" ? "UID / mid" : "频道 ID 或 URL"}>
              <input
                className={inputCls}
                required
                placeholder={
                  videoForm.type === "bilibili" ? "例如 12345678" : "UC… 或 https://youtube.com/@"
                }
                value={videoForm.account}
                onChange={(e) => setVideoForm((f) => ({ ...f, account: e.target.value }))}
                disabled={busy}
              />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            >
              {videoForm.id ? "保存账号" : "绑定账号"}
            </button>
            {videoForm.id ? (
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
                onClick={() =>
                  setVideoForm({ id: null, name: "", type: "bilibili", account: "" })
                }
              >
                取消编辑
              </button>
            ) : null}
          </div>
        </form>
      </section>
    </div>
  );
}
