import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Proxy /api/* → FastAPI backend.
  // V local devu frontend:3000 → backend:8000 (same-origin cookies, žádné CORS problémy).
  // V produkci Caddy routuje /api → backend kontejner přímo.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
