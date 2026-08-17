"use client";

import { FormEvent, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type CliEntry = {
  cmd: string;
  desc: string;
};

type CliGroup = {
  title: string;
  tool: string;
  note?: string;
  entries: CliEntry[];
};

const CLI_GROUPS: CliGroup[] = [
  {
    title: "统一入口",
    tool: "newsc",
    note: "HTTP → orchestrator；全局参数写在子命令前，如 newsc --format json health",
    entries: [
      { cmd: "newsc --format json health", desc: "健康检查" },
      { cmd: "newsc --format json pipeline run rss|youtube|bilibili|all-demo|sources", desc: "跑采集管道（sources 消费启用订阅）" },
      { cmd: "newsc --format json pipeline run insight --force", desc: "事件/宏观检索入库（可 --kind event|macro）" },
      { cmd: "newsc --format json ai process --limit 20", desc: "处理 AI Jobs（可用 --no-digest）" },
      { cmd: "newsc --format json vault status", desc: "日报 vault 状态" },
      { cmd: "newsc --format json vault files --source <id>", desc: "列出 vault HTML" },
      { cmd: "newsc --format json vault file --source <id> --path <file>", desc: "读取单个 HTML" },
      { cmd: "newsc --format json digest today", desc: "今日洞察" },
      { cmd: "newsc --format json items --limit 20", desc: "条目列表" },
      { cmd: "newsc --format json sources list|add|update|enable|disable|delete", desc: "订阅源 CRUD" },
      { cmd: "newsc --format json vault-source add|enable|disable|delete", desc: "digest-sources.yml 来源管理" },
    ],
  },
  {
    title: "云端库同步",
    tool: "scripts/deploy",
    note: "Mac 真源 → 云端 stock-pg/newsc 副本；配置写在 .env.cloud.local",
    entries: [
      { cmd: "bash scripts/deploy/db-tunnel.sh -d", desc: "确保 SSH 隧道（默认本机 15434）" },
      { cmd: "bash scripts/deploy/push-db-to-cloud.sh", desc: "vault ingest → pg_dump → 云端 restore" },
      { cmd: "bash scripts/deploy/push-db-to-cloud.sh --dry-run", desc: "只 dump / 对账，不写云" },
      { cmd: "bash scripts/deploy/pull-cloud-control.sh", desc: "拉云端 marks + 消费 outbox（A/B/C）" },
      { cmd: "bash scripts/deploy/install-cloud-bridge-launchd.sh", desc: "安装每 2 分钟控制面 Agent" },
      { cmd: "bash scripts/deploy/install-push-db-launchd.sh", desc: "按 .env.cloud.local 安装定时推送" },
      { cmd: "bash scripts/deploy/install-push-db-launchd.sh uninstall", desc: "卸载定时推送 LaunchAgent" },
    ],
  },
  {
    title: "采集专项",
    tool: "newsc-rss / youtube / bilibili",
    note: "默认 POST /ingest/batch；开发可用 --local-db",
    entries: [
      { cmd: "newsc-rss demo", desc: "RSS Demo 入库" },
      { cmd: "newsc-rss fetch --url <feed>", desc: "拉取 RSS/Atom" },
      { cmd: "newsc-youtube demo", desc: "YouTube Demo（仅 embed 元数据）" },
      { cmd: "newsc-youtube fetch --video-id <id>", desc: "按视频 ID 入库" },
      { cmd: "newsc-bilibili demo", desc: "B 站 Demo（仅 embed 元数据）" },
      { cmd: "newsc-bilibili fetch --bvid <BV…>", desc: "按 BV 号入库" },
    ],
  },
  {
    title: "日报",
    tool: "newsc-digest",
    note: "主路径 vault 只读；push 为兼容",
    entries: [
      { cmd: "newsc-digest vault status", desc: "vault 状态（主路径）" },
      { cmd: "newsc-digest vault files [--source <id>]", desc: "列出 HTML" },
      { cmd: "newsc-digest vault get --source <id> --path <file>", desc: "读取 HTML" },
      { cmd: "newsc-digest get today", desc: "今日日报 JSON" },
      { cmd: "newsc-digest push --demo|--file <html>", desc: "兼容：推送 HTML 入库" },
    ],
  },
];

const inputCls =
  "w-full rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]";

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      <div className="mt-1">{children}</div>
      {hint ? <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p> : null}
    </label>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="shrink-0 text-xs text-[var(--muted)] underline-offset-2 hover:text-[var(--accent)] hover:underline"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        } catch {
          /* ignore */
        }
      }}
    >
      {copied ? "已复制" : "复制"}
    </button>
  );
}

type CloudForm = {
  deploy_host: string;
  deploy_dir: string;
  tunnel_local_port: string;
  cloud_database_url: string;
  local_database_url: string;
  push_schedule_enabled: boolean;
  push_schedule_mode: "daily" | "interval";
  push_schedule_times: string;
  push_schedule_interval_hours: string;
};

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; ai_provider: string } | null>(null);
  const [form, setForm] = useState<CloudForm>({
    deploy_host: "120.25.145.131",
    deploy_dir: "/opt/newsc",
    tunnel_local_port: "15434",
    cloud_database_url: "",
    local_database_url: "postgresql://qiubin@/newsc?host=/tmp",
    push_schedule_enabled: false,
    push_schedule_mode: "daily",
    push_schedule_times: "09:00,12:00,16:00,20:00",
    push_schedule_interval_hours: "6",
  });
  const [configured, setConfigured] = useState(false);
  const [tunnelUp, setTunnelUp] = useState<boolean | null>(null);
  const [scheduleInstalled, setScheduleInstalled] = useState(false);
  const [logTail, setLogTail] = useState<string[]>([]);
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);

  function applyConfig(c: Awaited<ReturnType<typeof api.cloudSyncConfig>>) {
    setConfigured(c.configured);
    setTunnelUp(c.tunnel_up);
    setScheduleInstalled(c.push_schedule_installed);
    setForm({
      deploy_host: c.deploy_host,
      deploy_dir: c.deploy_dir,
      tunnel_local_port: String(c.tunnel_local_port),
      cloud_database_url: c.cloud_database_url,
      local_database_url: c.local_database_url,
      push_schedule_enabled: c.push_schedule_enabled,
      push_schedule_mode: c.push_schedule_mode,
      push_schedule_times: (c.push_schedule_times || []).join(","),
      push_schedule_interval_hours: String(c.push_schedule_interval_hours),
    });
    setLogTail(c.last_push?.tail ?? []);
  }

  async function refresh() {
    const [h, c] = await Promise.all([api.health(), api.cloudSyncConfig()]);
    setHealth(h);
    applyConfig(c);
  }

  useEffect(() => {
    refresh().catch((e) => {
      console.error(e);
      setLog(`加载失败：${e instanceof Error ? e.message : e}`);
    });
  }, []);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setLog(`${label}…`);
    try {
      const r = await fn();
      setLog(`${label} 完成：${JSON.stringify(r).slice(0, 4000)}`);
      await refresh();
    } catch (e) {
      setLog(`${label} 失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  }

  function onSave(e: FormEvent) {
    e.preventDefault();
    const port = Number(form.tunnel_local_port);
    if (!Number.isFinite(port) || port < 1024 || port > 65535) {
      setLog("隧道本机端口无效（1024–65535）");
      return;
    }
    const interval = Number(form.push_schedule_interval_hours);
    if (
      form.push_schedule_enabled &&
      form.push_schedule_mode === "interval" &&
      (!Number.isFinite(interval) || interval < 1 || interval > 168)
    ) {
      setLog("推送间隔无效（1–168 小时）");
      return;
    }
    const times = form.push_schedule_times
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (form.push_schedule_enabled && form.push_schedule_mode === "daily" && times.length === 0) {
      setLog("每日定点至少填写一个时刻（如 09:00）");
      return;
    }
    void run("保存云端同步配置", () =>
      api.saveCloudSyncConfig({
        deploy_host: form.deploy_host.trim(),
        deploy_dir: form.deploy_dir.trim(),
        tunnel_local_port: port,
        cloud_database_url: form.cloud_database_url.trim(),
        local_database_url: form.local_database_url.trim(),
        push_schedule_enabled: form.push_schedule_enabled,
        push_schedule_mode: form.push_schedule_mode,
        push_schedule_times: times,
        push_schedule_interval_hours: Number.isFinite(interval) ? interval : 6,
        apply_schedule: true,
      })
    );
  }

  return (
    <div className="animate-fade-up w-full space-y-10">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-3xl">设置</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          系统状态与采集运维。信源请到{" "}
          <Link href="/subscribe" className="text-[var(--accent)] underline-offset-2 hover:underline">
            订阅
          </Link>{" "}
          管理。
        </p>
      </header>

      <section className="rounded-md bg-[var(--surface)] px-4 py-3 text-sm">
        <div>API：{health?.ok ? "正常" : "未知"}</div>
        <div>AI Provider：{health?.ai_provider ?? "—"}</div>
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">事件与数据</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            按 <code className="text-[var(--ink)]">insight-queries.yml</code>{" "}
            检索入库，供「事件」「数据」页展示。真模式走当前 AI Provider。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            onClick={() => run("检索事件+数据", () => api.runInsight({ force: true, kind: "all" }))}
          >
            立即检索（全部）
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
            onClick={() => run("仅检索事件", () => api.runInsight({ force: true, kind: "event" }))}
          >
            仅事件
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
            onClick={() => run("仅检索宏观", () => api.runInsight({ force: true, kind: "macro" }))}
          >
            仅数据
          </button>
          <Link
            href="/events"
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm text-[var(--body)]"
          >
            打开事件
          </Link>
          <Link
            href="/data"
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm text-[var(--body)]"
          >
            打开数据
          </Link>
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">云端服务数据库同步</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Mac 为本机真源，经 SSH 隧道推送到云端{" "}
            <code className="text-[var(--ink)]">stock-pg / newsc</code>
            。配置写入{" "}
            <code className="text-[var(--ink)]">.env.cloud.local</code>
            （勿提交）。云端页面的星标 / 订阅 / 推库指令经 outbox 回写 Mac（需安装{" "}
            <code className="text-[var(--ink)]">install-cloud-bridge-launchd.sh</code>
            ）。
          </p>
        </div>

        <div className="flex flex-wrap gap-3 text-sm">
          <span>
            配置：
            <span className={configured ? "text-[var(--accent)]" : "text-[var(--muted)]"}>
              {configured ? "已就绪" : "未配置"}
            </span>
          </span>
          <span>
            隧道：
            <span className={tunnelUp === true ? "text-[var(--accent)]" : "text-[var(--muted)]"}>
              {tunnelUp === true ? "已连通" : tunnelUp === false ? "未监听" : "未知"}
            </span>
          </span>
          <span>
            定时推送：
            <span className={scheduleInstalled ? "text-[var(--accent)]" : "text-[var(--muted)]"}>
              {scheduleInstalled ? "LaunchAgent 已安装" : "未安装"}
            </span>
          </span>
        </div>

        <form className="space-y-3" onSubmit={onSave}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="云端主机 DEPLOY_HOST">
              <input
                className={inputCls}
                value={form.deploy_host}
                onChange={(e) => setForm((f) => ({ ...f, deploy_host: e.target.value }))}
                placeholder="120.25.145.131"
                autoComplete="off"
              />
            </Field>
            <Field label="远端目录 DEPLOY_DIR">
              <input
                className={inputCls}
                value={form.deploy_dir}
                onChange={(e) => setForm((f) => ({ ...f, deploy_dir: e.target.value }))}
                placeholder="/opt/newsc"
                autoComplete="off"
              />
            </Field>
            <Field label="隧道本机端口" hint="默认 15434（避开 stock 15432 / FlowLedger 15433）">
              <input
                className={inputCls}
                value={form.tunnel_local_port}
                onChange={(e) => setForm((f) => ({ ...f, tunnel_local_port: e.target.value }))}
                inputMode="numeric"
                autoComplete="off"
              />
            </Field>
            <Field label="本机库 LOCAL_DATABASE_URL">
              <input
                className={inputCls}
                value={form.local_database_url}
                onChange={(e) => setForm((f) => ({ ...f, local_database_url: e.target.value }))}
                autoComplete="off"
              />
            </Field>
          </div>
          <Field
            label="云端库 CLOUD_DATABASE_URL"
            hint="经隧道访问，如 postgresql://newsc:密码@127.0.0.1:15434/newsc；已保存密码显示为 ***，留空保存则保留原值"
          >
            <input
              className={inputCls}
              value={form.cloud_database_url}
              onChange={(e) => setForm((f) => ({ ...f, cloud_database_url: e.target.value }))}
              placeholder="postgresql://newsc:***@127.0.0.1:15434/newsc"
              autoComplete="off"
            />
          </Field>

          <div className="space-y-3 rounded-md border border-[var(--line)] px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-[var(--ink)]">定时推送</h3>
              <label className="flex items-center gap-2 text-sm text-[var(--body)]">
                <input
                  type="checkbox"
                  checked={form.push_schedule_enabled}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, push_schedule_enabled: e.target.checked }))
                  }
                />
                启用（写入 Mac LaunchAgent）
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="周期模式">
                <select
                  className={inputCls}
                  value={form.push_schedule_mode}
                  disabled={!form.push_schedule_enabled}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      push_schedule_mode: e.target.value as "daily" | "interval",
                    }))
                  }
                >
                  <option value="daily">每日定点</option>
                  <option value="interval">按小时间隔</option>
                </select>
              </Field>
              {form.push_schedule_mode === "interval" ? (
                <Field label="间隔（小时）" hint="1–168，如 6 = 每 6 小时">
                  <input
                    className={inputCls}
                    value={form.push_schedule_interval_hours}
                    disabled={!form.push_schedule_enabled}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, push_schedule_interval_hours: e.target.value }))
                    }
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </Field>
              ) : (
                <Field
                  label="推送时刻"
                  hint="逗号分隔，如 09:00,12:00,16:00,20:00"
                >
                  <input
                    className={inputCls}
                    value={form.push_schedule_times}
                    disabled={!form.push_schedule_enabled}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, push_schedule_times: e.target.value }))
                    }
                    placeholder="09:00,12:00,16:00,20:00"
                    autoComplete="off"
                  />
                </Field>
              )}
            </div>
            <p className="text-xs text-[var(--muted)]">
              保存时自动安装或卸载{" "}
              <code className="text-[var(--ink)]">com.newsc.push-db-cloud</code>
              。本机锁屏/关机时不会触发。
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            >
              保存配置
            </button>
            <button
              type="button"
              disabled={busy}
              className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
              onClick={() => run("启动隧道", () => api.ensureCloudTunnel())}
            >
              启动隧道
            </button>
            <button
              type="button"
              disabled={busy || !configured}
              className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
              onClick={() => run("推库 dry-run", () => api.pushDbToCloud(true))}
            >
              Dry-run
            </button>
            <button
              type="button"
              disabled={busy || !configured}
              className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
              onClick={() => {
                if (!window.confirm("将本机 newsc 整库推送到云端（覆盖云端副本）。确认？")) return;
                void run("推送到云端", () => api.pushDbToCloud(false));
              }}
            >
              推送到云端
            </button>
          </div>
        </form>

        {log ? (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-[var(--surface)] px-3 py-2 text-xs text-[var(--body)]">
            {log}
          </pre>
        ) : null}

        {logTail.length > 0 ? (
          <details className="text-sm">
            <summary className="cursor-pointer text-[var(--muted)]">最近推送日志</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-[var(--body)]">
              {logTail.join("\n")}
            </pre>
          </details>
        ) : null}
      </section>

      <section className="space-y-6">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-xl">CLI 能力</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            本机终端 / Cron / Agent 调用。先{" "}
            <code className="text-[var(--ink)]">pip install -e .</code>
            ，API 默认{" "}
            <code className="text-[var(--ink)]">http://127.0.0.1:8787</code>
            。退出码：0 成功 / 2 空 / 3 API / 4 校验。
          </p>
        </div>

        {CLI_GROUPS.map((group) => (
          <div key={group.tool} className="space-y-3">
            <div>
              <h3 className="text-sm font-medium text-[var(--ink)]">
                {group.title}
                <span className="ml-2 font-normal text-[var(--muted)]">{group.tool}</span>
              </h3>
              {group.note ? <p className="mt-0.5 text-xs text-[var(--muted)]">{group.note}</p> : null}
            </div>
            <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
              {group.entries.map((row) => (
                <li
                  key={row.cmd}
                  className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
                >
                  <div className="min-w-0 flex-1">
                    <code className="block break-all text-[13px] leading-snug text-[var(--ink)]">
                      {row.cmd}
                    </code>
                    <p className="mt-0.5 text-xs text-[var(--muted)]">{row.desc}</p>
                  </div>
                  <CopyButton text={row.cmd} />
                </li>
              ))}
            </ul>
          </div>
        ))}

        <p className="text-xs text-[var(--muted)]">
          文档：仓库{" "}
          <code className="text-[var(--body)]">guide/CLI一页.md</code>、
          <code className="text-[var(--body)]">guide/混合部署与云端运维.md</code>
          。
        </p>
      </section>
    </div>
  );
}
