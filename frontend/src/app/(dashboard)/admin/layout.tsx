"use client";

/**
 * Admin guard — všechny stránky pod /admin/* musí být platform admin only.
 *
 * Backend endpointy /admin/* jsou chráněné `require_platform_admin()`, ale
 * frontend musí taky guardovat, aby se OZO/HR users vůbec nedostali na admin
 * UI (defense-in-depth + UX — neukazovat info o existenci admin sekce).
 *
 * Strategie:
 * 1. Načti /auth/me přes useQuery (cached → fast)
 * 2. Pokud is_platform_admin !== true → redirect na /dashboard
 * 3. Dokud načítá → ukaž minimální loader (žádný admin obsah)
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { UserResponse } from "@/types/api";

export default function AdminGuardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();

  const { data: user, isLoading, isError } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 60_000,
  });

  const isAuthorized = user?.is_platform_admin === true;

  useEffect(() => {
    if (isLoading) return;
    // Pokud /auth/me selže (401 → redirect na /login zařídí api.ts)
    if (isError) return;
    if (!isAuthorized) {
      router.replace("/dashboard");
    }
  }, [isLoading, isError, isAuthorized, router]);

  if (isLoading || !isAuthorized) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Ověřuji oprávnění…
      </div>
    );
  }

  return <>{children}</>;
}
