"use client";

/**
 * OZO multi-client overview.
 *
 * Default landing page po loginu OZO. Tabulka klientů s agregátem
 * expirujících událostí napříč moduly. Klik na řádek přepne kontext
 * (POST /auth/select-tenant) a otevře dashboard daného klienta.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Briefcase, AlertTriangle, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import type { ClientOverview, UserResponse } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function MetricBadge({ label, value, urgent }: { label: string; value: number; urgent?: boolean }) {
  if (value === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-gray-300">
        <span>{label}</span>
        <span className="font-mono">0</span>
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        urgent
          ? "bg-red-50 text-red-700"
          : "bg-amber-50 text-amber-700"
      )}
    >
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </span>
  );
}

export default function MyClientsPage() {
  const qc = useQueryClient();
  const router = useRouter();

  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
  });

  const { data: clients = [], isLoading } = useQuery<ClientOverview[]>({
    queryKey: ["ozo-overview"],
    queryFn: () => api.get("/ozo/overview"),
  });

  const switchTo = useMutation({
    mutationFn: (tenant_id: string) =>
      api.post<{ access_token: string }>("/auth/select-tenant", { tenant_id }),
    onSuccess: async (resp) => {
      if (typeof document !== "undefined" && resp.access_token) {
        document.cookie = `access_token=${resp.access_token}; path=/; max-age=1800`;
      }
      await qc.invalidateQueries();
      router.push("/dashboard");
    },
  });

  const totalActions = clients.reduce((s, c) => s + c.total_actions, 0);

  return (
    <div>
      <Header title="Moji klienti" />

      <div className="p-6 space-y-4">
        {/* Summary banner */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Přehled OZO {user?.full_name || user?.email || ""}
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {clients.length} {clients.length === 1 ? "klient" : clients.length < 5 ? "klienti" : "klientů"}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Akce v příštích 30 dnech
                </p>
                <p
                  className={cn(
                    "mt-1 text-2xl font-bold",
                    totalActions > 10 ? "text-red-600" : totalActions > 0 ? "text-amber-600" : "text-green-600"
                  )}
                >
                  {totalActions}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Klient table */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-16 animate-pulse bg-gray-50 rounded" />
                ))}
              </div>
            ) : clients.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                <Briefcase className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Zatím žádní klienti</p>
                <p className="text-xs mt-1">Platform admin tě přiřadí ke klientům přes /admin/tenants</p>
              </div>
            ) : (
              <ul className="divide-y divide-gray-100">
                {clients.map((c) => {
                  const isCurrent = c.tenant_id === user?.tenant_id;
                  return (
                    <li key={c.tenant_id}>
                      <button
                        onClick={() => switchTo.mutate(c.tenant_id)}
                        disabled={switchTo.isPending}
                        className={cn(
                          "w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors flex items-center justify-between gap-4",
                          isCurrent && "bg-blue-50/30",
                          switchTo.isPending && "opacity-50 cursor-wait"
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <div className={cn(
                            "h-10 w-10 rounded-md flex items-center justify-center shrink-0",
                            c.total_actions === 0 ? "bg-green-100" :
                            c.total_actions > 10 ? "bg-red-100" : "bg-amber-100"
                          )}>
                            {c.total_actions === 0 ? (
                              <Briefcase className="h-5 w-5 text-green-600" />
                            ) : (
                              <AlertTriangle className={cn(
                                "h-5 w-5",
                                c.total_actions > 10 ? "text-red-600" : "text-amber-600"
                              )} />
                            )}
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-gray-900 truncate">
                                {c.tenant_name}
                              </span>
                              {isCurrent && (
                                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                                  aktivní
                                </span>
                              )}
                            </div>
                            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                              <MetricBadge
                                label="školení"
                                value={c.metrics.expiring_trainings}
                              />
                              <MetricBadge
                                label="LP"
                                value={c.metrics.expiring_medical_exams}
                              />
                              <MetricBadge
                                label="revize"
                                value={c.metrics.due_revisions}
                                urgent={c.metrics.overdue_revisions > 0}
                              />
                              <MetricBadge
                                label="OOPP"
                                value={c.metrics.expiring_oopp}
                              />
                              <MetricBadge
                                label="úrazy draft"
                                value={c.metrics.draft_accident_reports}
                              />
                            </div>
                          </div>
                        </div>

                        <ChevronRight className="h-5 w-5 text-gray-400 shrink-0" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <p className="text-xs text-gray-400 text-center pt-2">
          Klikni na klienta pro otevření jeho dashboardu. Klienti jsou seřazeni
          podle počtu otevřených úkolů (nejvíc nahoře).
        </p>
      </div>
    </div>
  );
}
