/**
 * 同源 /api/* → orchestrator，服务端注入 ORCH_API_TOKEN。
 * 避免浏览器直连写接口 401，且不把 token 暴露给前端。
 */
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ORCH = (process.env.ORCH_INTERNAL_URL || "http://127.0.0.1:8787").replace(/\/$/, "");
const TOKEN = (process.env.ORCH_API_TOKEN || "").trim();

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { path } = await ctx.params;
  const segments = Array.isArray(path) ? path : [];
  if (segments.length === 0) {
    return NextResponse.json({ detail: "missing path" }, { status: 400 });
  }
  const target = `${ORCH}/${segments.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);
  if (TOKEN) {
    headers.set("Authorization", `Bearer ${TOKEN}`);
    headers.set("X-API-Token", TOKEN);
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (err) {
    console.error("[api-proxy] upstream_fail", req.method, target, err);
    return NextResponse.json(
      { detail: "orchestrator unreachable" },
      { status: 502 }
    );
  }

  if (upstream.status === 401) {
    console.warn("[api-proxy] upstream_401", req.method, `/${segments.join("/")}`, "token_set=", Boolean(TOKEN));
  }

  const out = new Headers();
  const resCt = upstream.headers.get("content-type");
  if (resCt) out.set("content-type", resCt);
  const body = await upstream.arrayBuffer();
  return new NextResponse(body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
