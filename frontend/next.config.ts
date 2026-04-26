import type { NextConfig } from "next";

// Server-side proxy cíl: Next.js server (uvnitř docker kontejneru) musí použít
// docker network hostname `backend`. `localhost` uvnitř kontejneru by ukazoval
// na frontend sám. Mimo docker (npm run dev na hostu) stačí localhost.
// NEXT_PUBLIC_API_URL je pro browser (dnes nepoužito, všechno jde přes /api/*).
const INTERNAL_BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Proxy /api/* → FastAPI backend.
  // V local devu frontend:3000 → backend:8000 (same-origin cookies, žádné CORS problémy).
  // V produkci Caddy routuje /api → backend kontejner přímo.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${INTERNAL_BACKEND_URL}/api/:path*`,
      },
    ];
  },

  // PWA — service worker musí mít Cache-Control: no-cache, ať se update načte
  // při každém otevření aplikace. Service-Worker-Allowed: / dovoluje řídit
  // celý origin (nejen /sw.js scope).
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
        ],
      },
      {
        source: "/manifest.json",
        headers: [
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
    ];
  },
};

export default nextConfig;
