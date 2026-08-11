"use client";

import { useEffect, useState } from "react";
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

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; ai_provider: string } | null>(null);
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const h = await api.health();
    setHealth(h);
  }

  useEffect(() => {
    refresh().catch(console.error);
  }, []);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setLog(`${label}…`);
    try {
      const r = await fn();
      setLog(`${label} 完成：${JSON.stringify(r)}`);
      await refresh();
    } catch (e) {
      setLog(`${label} 失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
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

      <section className="space-y-2">
        <h2 className="font-[family-name:var(--font-display)] text-xl">一键演示</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] disabled:opacity-50"
            onClick={() => run("采集 all-demo", () => api.runPipeline("all-demo"))}
          >
            采集 Demo
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-50"
            onClick={() => run("AI 批处理", () => api.processAi())}
          >
            处理 AI Jobs
          </button>
        </div>
        {log ? <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-[var(--body)]">{log}</pre> : null}
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
          <code className="text-[var(--body)]">ADR/006-unified-newsc-cli.md</code>
          。Cron 示例见{" "}
          <code className="text-[var(--body)]">guide/运维与Cron.md</code>。
        </p>
      </section>
    </div>
  );
}
