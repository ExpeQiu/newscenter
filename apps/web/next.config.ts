import type { NextConfig } from "next";

const orchInternal =
  process.env.ORCH_INTERNAL_URL?.replace(/\/$/, "") || "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${orchInternal}/:path*`,
      },
    ];
  },
};

export default nextConfig;
