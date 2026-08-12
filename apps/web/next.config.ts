import type { NextConfig } from "next";

/**
 * /api/* 由 app/api/[...path]/route.ts 代理（注入 ORCH_API_TOKEN）。
 * 不再用 rewrite，避免绕过鉴权头。
 */
const nextConfig: NextConfig = {
  // 空配置保留扩展点
};

export default nextConfig;
