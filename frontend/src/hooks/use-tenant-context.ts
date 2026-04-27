"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface TenantContextResponse {
  slug: string | null;
  name: string | null;
  is_admin: string;  // "true" | "false" — endpoint serializuje jako string
}

export interface TenantContext {
  slug: string | null;
  name: string | null;
  isAdmin: boolean;
  isRoot: boolean;
}

/**
 * Vrátí tenant kontext z aktuální subdomény. Server endpoint
 * /auth/tenant-info je veřejný (žádná auth required) a vrací data podle
 * Host hlavičky requestu.
 *
 * Použití: branded login UI (logo firmy, název v hlavičce), conditional
 * routing v ClientSwitcher, redirect do /admin pro admin subdomain.
 */
export function useTenantContext(): TenantContext | undefined {
  const { data } = useQuery<TenantContextResponse>({
    queryKey: ["tenant-context"],
    queryFn: () => api.get("/auth/tenant-info"),
    staleTime: 10 * 60 * 1000,
  });
  if (!data) return undefined;
  return {
    slug: data.slug,
    name: data.name,
    isAdmin: data.is_admin === "true",
    isRoot: data.slug === null,
  };
}

/**
 * Vrátí URL pro daný tenant slug. Pro admin subdomain použij `null`.
 *
 * Příklad: subdomainUrl('strojirny-abc') → 'http://strojirny-abc.localhost:3000'
 */
export function subdomainUrl(slug: string | null, path: string = "/"): string {
  const scheme = process.env.NEXT_PUBLIC_APP_URL_SCHEME || "http";
  const baseDomain = (process.env.NEXT_PUBLIC_BASE_DOMAIN || ".localhost").replace(/^\./, "");
  const port = process.env.NEXT_PUBLIC_APP_URL_PORT || "";
  const sub = slug ? `${slug}.` : "";
  return `${scheme}://${sub}${baseDomain}${port}${path}`;
}
