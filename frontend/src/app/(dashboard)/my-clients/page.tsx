"use client";

/**
 * OZO multi-client overview.
 *
 * Default landing page po loginu OZO. Tabulka klientů s agregátem
 * expirujících událostí napříč moduly. Klik na řádek přepne kontext
 * (POST /auth/select-tenant) a otevře dashboard daného klienta.
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Briefcase, AlertTriangle, ChevronRight, Settings, Snowflake, Power, PowerOff,
} from "lucide-react";
import { api, ApiError, uploadFile } from "@/lib/api";
import type { ClientOverview, UserResponse } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
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
  const [settingsTenantId, setSettingsTenantId] = useState<string | null>(null);

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
                      <div className={cn(
                          "w-full px-5 py-4 hover:bg-gray-50 transition-colors flex items-center justify-between gap-4",
                          isCurrent && "bg-blue-50/30",
                          switchTo.isPending && "opacity-50",
                        )}>
                      <button
                        onClick={() => switchTo.mutate(c.tenant_id)}
                        disabled={switchTo.isPending}
                        className="text-left flex items-center gap-3 min-w-0 flex-1"
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
                      <button
                        onClick={() => setSettingsTenantId(c.tenant_id)}
                        className="rounded-md p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors shrink-0"
                        title="Nastavení klienta"
                      >
                        <Settings className="h-4 w-4" />
                      </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <ClientSettingsDialog
          tenantId={settingsTenantId}
          onClose={() => setSettingsTenantId(null)}
        />

        <p className="text-xs text-gray-400 text-center pt-2">
          Klikni na klienta pro otevření jeho dashboardu. Klienti jsou seřazeni
          podle počtu otevřených úkolů (nejvíc nahoře).
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ClientSettingsDialog — úprava klienta z /my-clients (kolečko Settings)
// Volá PATCH /admin/tenants/{id} → vyžaduje platform admin oprávnění.
// Pokud uživatel není platform admin, server vrátí 403 a UI to zobrazí.
// Logo upload není zatím napojen na API endpoint — pole je readonly s TODO.
// ─────────────────────────────────────────────────────────────────────────────

interface TenantDetail {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  logo_path: string | null;
  service_level: string | null;
  frozen_at: string | null;
  billing_address_street?: string | null;
  billing_address_city?: string | null;
  billing_address_zip?: string | null;
}

const SERVICE_LEVELS = [
  { value: "", label: "—" },
  { value: "free", label: "Free" },
  { value: "basic", label: "Basic" },
  { value: "standard", label: "Standard" },
  { value: "pro", label: "Pro" },
  { value: "enterprise", label: "Enterprise" },
];

function ClientSettingsDialog({
  tenantId,
  onClose,
}: {
  tenantId: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [zip, setZip] = useState("");
  const [serviceLevel, setServiceLevel] = useState<string>("");
  const [isFrozen, setIsFrozen] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);

  const open = tenantId !== null;

  const { data: tenant, isLoading } = useQuery<TenantDetail>({
    queryKey: ["admin-tenant-detail", tenantId],
    queryFn: () => api.get(`/admin/tenants/${tenantId}`),
    enabled: open,
  });

  // sync formuláře po načtení tenant detailu
  useEffect(() => {
    if (tenant) {
      setName(tenant.name);
      setStreet(tenant.billing_address_street || "");
      setCity(tenant.billing_address_city || "");
      setZip(tenant.billing_address_zip || "");
      setServiceLevel(tenant.service_level || "");
      setIsFrozen(!!tenant.frozen_at);
      setIsActive(tenant.is_active);
    }
  }, [tenant]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        name,
        billing_address_street: street || null,
        billing_address_city: city || null,
        billing_address_zip: zip || null,
        service_level: serviceLevel || null,
        is_frozen: isFrozen,
        is_active: isActive,
      };
      const updated = await api.patch<TenantDetail>(
        `/admin/tenants/${tenantId}`,
        body,
      );
      // Logo upload — pokud je vybrán, pošle se separátně přes UploadFile.
      // Endpoint zatím neexistuje, takže to jen no-op + warning v konzoli.
      if (logoFile) {
        try {
          await uploadFile(`/admin/tenants/${tenantId}/logo`, logoFile);
        } catch (e) {
          console.warn("Logo upload endpoint zatím neexistuje", e);
        }
      }
      return updated;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ozo-overview"] });
      qc.invalidateQueries({ queryKey: ["admin-tenant-detail", tenantId] });
      onClose();
    },
    onError: (e: unknown) => {
      if (e instanceof ApiError && e.status === 403) {
        setError("Pro úpravu nastavení klienta potřebuješ platform admin oprávnění.");
      } else {
        setError(e instanceof Error ? e.message : "Chyba při ukládání");
      }
    },
  });

  if (!open) return null;

  return (
    <Dialog open={open} onClose={onClose} title="Nastavení klienta">
      {isLoading ? (
        <div className="py-8 text-center text-sm text-gray-500">Načítám…</div>
      ) : (
        <div className="space-y-4">
          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="t-name">Název firmy *</Label>
            <Input id="t-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5 col-span-2">
              <Label htmlFor="t-street">Ulice a č.p.</Label>
              <Input id="t-street" value={street} onChange={(e) => setStreet(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="t-city">Město</Label>
              <Input id="t-city" value={city} onChange={(e) => setCity(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="t-zip">PSČ</Label>
              <Input id="t-zip" value={zip} onChange={(e) => setZip(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="t-logo">Logo firmy (PNG/JPG, max 1 MB)</Label>
            <input
              id="t-logo"
              type="file"
              accept="image/png,image/jpeg"
              onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-700 dark:text-gray-200
                         file:mr-3 file:py-1.5 file:px-3 file:rounded-md
                         file:border-0 file:text-xs file:font-medium
                         file:bg-blue-50 file:text-blue-700
                         hover:file:bg-blue-100"
            />
            {tenant?.logo_path && !logoFile && (
              <p className="text-xs text-gray-500">Aktuální logo: {tenant.logo_path}</p>
            )}
            <p className="text-xs text-amber-600">
              Pozn.: backend endpoint pro upload loga zatím neexistuje (TODO).
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="t-svc">Úroveň služeb</Label>
            <select
              id="t-svc"
              value={serviceLevel}
              onChange={(e) => setServiceLevel(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm
                         dark:bg-gray-800 dark:border-gray-600 dark:text-gray-100"
            >
              {SERVICE_LEVELS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium text-amber-900">
              <Snowflake className="h-4 w-4" />
              <input
                type="checkbox"
                checked={isFrozen}
                onChange={(e) => setIsFrozen(e.target.checked)}
                className="h-4 w-4"
              />
              Zmrazit klienta (read-only přístup, nelze upravovat)
            </label>
            <label className="flex items-center gap-2 text-sm font-medium text-amber-900">
              {isActive ? <Power className="h-4 w-4" /> : <PowerOff className="h-4 w-4" />}
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4"
              />
              Aktivní (odznačením úplně deaktivuješ — login zakázán)
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Zrušit
            </Button>
            <Button
              type="button"
              onClick={() => { setError(null); saveMut.mutate(); }}
              disabled={saveMut.isPending || !name.trim()}
            >
              {saveMut.isPending ? "Ukládám…" : "Uložit"}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
