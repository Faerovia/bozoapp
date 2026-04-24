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
};

export default nextConfig;
