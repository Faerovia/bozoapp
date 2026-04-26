"use client";

import "./globals.css";
import { useEffect } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/query-client";
import { PWAInstallPrompt } from "@/components/pwa-install-prompt";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Registrace service workeru — jen v produkčním buildu, dev mode by ho
  // jinak agresivně cachoval HMR moduly.
  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      process.env.NODE_ENV === "production"
    ) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch((err) => console.warn("SW registration failed:", err));
    }
  }, []);

  return (
    <html lang="cs">
      <head>
        <title>DigitalOZO</title>
        <meta name="description" content="DigitalOZO — BOZP a PO management platforma pro OZO" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#2563eb" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="DigitalOZO" />
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body>
        <QueryClientProvider client={queryClient}>
          {children}
          <PWAInstallPrompt />
        </QueryClientProvider>
      </body>
    </html>
  );
}
