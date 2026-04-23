import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Přísný mode pro lepší React error detection v dev
  reactStrictMode: true,

  // API proxy: v produkci Caddy routuje /api → backend,
  // v local devu přesměrujeme přes Next.js rewrites
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
