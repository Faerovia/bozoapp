"use client";

/**
 * Client switcher — dropdown v sidebaru pro OZO multi-client.
 *
 * Subdomain model: switch = redirect na druhý subdomain. JWT cookie je
 * sdílený mezi *.digitalozo.cz subdomains (settings.cookie_domain), takže
 * uživatel je rovnou přihlášený. Pokud cookie_domain nesdílí (dev),
 * fallback je /auth/select-tenant + reload na stejné stránce.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, ChevronDown, Check } from "lucide-react";
import { api } from "@/lib/api";
import type { Membership, UserResponse } from "@/types/api";
import { cn } from "@/lib/utils";
import { subdomainUrl } from "@/hooks/use-tenant-context";

export function ClientSwitcher() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 60_000,
  });

  const { data: memberships = [] } = useQuery<Membership[]>({
    queryKey: ["memberships"],
    queryFn: () => api.get("/auth/memberships"),
    staleTime: 60_000,
  });

  // Detekce, jestli cookie_domain umožní cross-subdomain SSO. Pokud ano,
  // můžeme prostě window.location.assign('https://druhy-tenant.digitalozo.cz/...')
  // a server tam nás přihlásí podle existující cookie. Pokud ne (dev),
  // zavoláme /auth/select-tenant a děláme reload.
  const cookieDomain = process.env.NEXT_PUBLIC_COOKIE_DOMAIN || "";
  const supportsCrossSubdomainSso = !!cookieDomain;

  const selectTenant = useMutation({
    mutationFn: (membership: Membership) => {
      if (supportsCrossSubdomainSso) {
        // Subdomain redirect — JWT cookie přejde s námi
        return Promise.resolve(membership);
      }
      // Same-subdomain mode: vyměníme JWT za nový s vybraným tenant_id
      return api.post<{ access_token: string }>("/auth/select-tenant", {
        tenant_id: membership.tenant_id,
      }).then(() => membership);
    },
    onSuccess: async (membership: Membership) => {
      if (supportsCrossSubdomainSso) {
        const url = subdomainUrl(membership.tenant_slug, "/dashboard");
        window.location.assign(url);
        return;
      }
      await qc.invalidateQueries();
      setOpen(false);
      if (typeof window !== "undefined") window.location.reload();
    },
  });

  // Nezobrazuj switcher pokud user má jen 1 klienta (nebo 0)
  if (memberships.length <= 1) {
    return null;
  }

  const current = memberships.find((m) => m.tenant_id === user?.tenant_id);

  return (
    <div className="relative px-3 pt-3 pb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between rounded-md border border-gray-200 px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <Building2 className="h-4 w-4 text-blue-500 shrink-0" />
          <span className="truncate text-left font-medium text-gray-800">
            {current?.tenant_name ?? "Vyber klienta"}
          </span>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-gray-400 transition-transform shrink-0",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="absolute left-3 right-3 top-full mt-1 max-h-72 overflow-auto rounded-md border border-gray-200 bg-white shadow-lg z-50">
          <div className="px-3 py-1.5 text-xs uppercase tracking-wide text-gray-400 border-b border-gray-100">
            Tvoji klienti ({memberships.length})
          </div>
          {memberships.map((m) => {
            const isCurrent = m.tenant_id === user?.tenant_id;
            return (
              <button
                key={m.tenant_id}
                onClick={() => selectTenant.mutate(m)}
                disabled={isCurrent || selectTenant.isPending}
                className={cn(
                  "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors",
                  isCurrent
                    ? "bg-blue-50 text-blue-700"
                    : "hover:bg-gray-50 text-gray-700",
                  selectTenant.isPending && "opacity-50 cursor-wait"
                )}
              >
                <div className="flex flex-col min-w-0">
                  <span className="truncate font-medium">{m.tenant_name}</span>
                  <span className="text-xs text-gray-400">{m.role}</span>
                </div>
                {isCurrent && <Check className="h-4 w-4 text-blue-600 shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
