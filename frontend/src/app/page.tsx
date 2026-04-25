"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

/**
 * Root redirect podle role.
 * - platform admin (is_platform_admin=true) → /admin
 * - běžný user → /dashboard
 *
 * Middleware už ošetřil že tu není user bez tokenu.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.get<{ role: string; is_platform_admin: boolean }>("/auth/me");
        if (cancelled) return;
        router.replace(me.is_platform_admin ? "/admin" : "/dashboard");
      } catch {
        if (!cancelled) router.replace("/dashboard");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return null;
}
