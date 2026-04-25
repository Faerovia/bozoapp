"use client";

/**
 * Platform admin dashboard — přehled všech tenantů, počet zákazníků (employees)
 * pro billing, tlačítko impersonate pro přepnutí do tenantu.
 *
 * Přístup: jen pro uživatele s is_platform_admin=True.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Building2, Users, Briefcase, GraduationCap, ExternalLink, AlertTriangle, Loader2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

interface TenantOverviewItem {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  employee_count: number;
  user_count: number;
  workplace_count: number;
  training_assignment_count: number;
}

interface TenantOverviewResponse {
  total_tenants: number;
  total_employees: number;
  tenants: TenantOverviewItem[];
}

interface ImpersonateResponse {
  access_token: string;
  tenant_id: string;
  tenant_name: string;
}

export default function AdminPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<TenantOverviewResponse>({
    queryKey: ["admin-tenant-overview"],
    queryFn: () => api.get("/admin/tenant-overview"),
    refetchInterval: 60_000,
  });

  const impersonateMutation = useMutation({
    mutationFn: (tenantId: string) => api.post<ImpersonateResponse>(
      "/admin/impersonate-tenant", { tenant_id: tenantId },
    ),
    onSuccess: (data) => {
      // Uloží access token a presměruje na dashboard tenantu.
      // Token je v cookie (httpOnly) — backend ho nastavil přes Set-Cookie?
      // Endpoint vrací jen access_token v body. Ukládáme do localStorage
      // pro Bearer header.
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("impersonating_tenant", data.tenant_name);
      router.push("/dashboard");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  if (isError) {
    return (
      <div>
        <Header title="Platform admin" />
        <div className="p-6">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 inline mr-2" />
            Nemáte oprávnění platform admin (is_platform_admin=true).
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header title="Platform admin — přehled tenantů" />

      <div className="p-6 space-y-4">
        {/* Souhrn */}
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Celkem tenantů</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">
                {data?.total_tenants ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                Celkem zaměstnanců (zákazníků)
              </p>
              <p className="text-3xl font-bold text-blue-700 mt-1">
                {data?.total_employees ?? "—"}
              </p>
            </CardContent>
          </Card>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Tabulka tenantů */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Načítám…
              </div>
            ) : !data || data.tenants.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Building2 className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádní tenanti</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Tenant</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Vytvořeno</th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <Users className="h-3.5 w-3.5 inline mr-1" /> Zaměstnanci
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        Uživatelé
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <Briefcase className="h-3.5 w-3.5 inline mr-1" /> Pracoviště
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <GraduationCap className="h-3.5 w-3.5 inline mr-1" /> Školení
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {data.tenants.map(t => (
                      <tr key={t.id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-900">{t.name}</td>
                        <td className="py-3 px-4 text-xs text-gray-600">{formatDate(t.created_at)}</td>
                        <td className="py-3 px-4 text-right font-bold text-blue-700">{t.employee_count}</td>
                        <td className="py-3 px-4 text-right text-gray-600">{t.user_count}</td>
                        <td className="py-3 px-4 text-right text-gray-600">{t.workplace_count}</td>
                        <td className="py-3 px-4 text-right text-gray-600">{t.training_assignment_count}</td>
                        <td className="py-3 px-4">
                          {t.is_active ? (
                            <span className="rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-[11px] font-medium">
                              Aktivní
                            </span>
                          ) : (
                            <span className="rounded-full bg-gray-100 text-gray-500 px-2 py-0.5 text-[11px] font-medium">
                              Pozastaven
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Tooltip label="Přepnout do tenantu (impersonate)">
                            <button
                              onClick={() => impersonateMutation.mutate(t.id)}
                              className="rounded p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                              aria-label="Impersonate"
                              disabled={impersonateMutation.isPending}
                            >
                              <ExternalLink className="h-4 w-4" />
                            </button>
                          </Tooltip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          <strong>Pricing tip:</strong> sloupec &bdquo;Zaměstnanci&ldquo; ukazuje
          počet aktivních zaměstnanců tenanta — slouží jako základ pro výpočet
          předplatného. Klik na ikonu &bdquo;externí odkaz&ldquo; přepne do tenantu
          (impersonate) — uvidíte data z pohledu OZO té firmy.
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
            Další admin funkce (připravujeme)
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-md border border-gray-200 bg-white p-4">
              <p className="text-sm font-medium text-gray-900">Globální nastavení</p>
              <p className="text-xs text-gray-500 mt-1">
                Nastavení pravidel pro lhůty prohlídek, šablony dokumentů, atd.
              </p>
              <Button size="sm" variant="outline" disabled className="mt-2">
                Brzy
              </Button>
            </div>
            <div className="rounded-md border border-gray-200 bg-white p-4">
              <p className="text-sm font-medium text-gray-900">Globální školení</p>
              <p className="text-xs text-gray-500 mt-1">
                Vytvářet školení dostupná všem tenantům na &bdquo;marketplace&ldquo;.
              </p>
              <Button size="sm" variant="outline" disabled className="mt-2">
                Brzy
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
