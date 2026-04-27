"use client";

/**
 * Platform admin — přehled zákazníků (tenantů) + správa fakturace.
 * Klik na řádek = expand s formulářem pro typ platby a fakturovanou částku.
 */

import { Fragment, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, Briefcase, GraduationCap, ExternalLink, AlertTriangle,
  Loader2, ChevronDown, ChevronRight, Save, CreditCard, Plus, Building2,
  Globe,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { SubdomainEditor } from "@/components/admin/subdomain-editor";

interface TenantOverviewItem {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  employee_count: number;
  user_count: number;
  workplace_count: number;
  training_assignment_count: number;
  billing_type: string | null;
  billing_amount: number | null;
  billing_currency: string;
  billing_note: string | null;
  // Fakturační údaje příjemce — povinné pro vystavení faktury
  billing_company_name: string | null;
  billing_ico: string | null;
  billing_dic: string | null;
  billing_address_street: string | null;
  billing_address_city: string | null;
  billing_address_zip: string | null;
  billing_email: string | null;
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

const BILLING_TYPE_LABELS: Record<string, string> = {
  monthly:      "Měsíční paušál",
  yearly:       "Roční paušál",
  per_employee: "Za zaměstnance / měsíc",
  custom:       "Vlastní (viz poznámka)",
  free:         "Zdarma",
};

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Billing editor uvnitř expanded row ───────────────────────────────────────

function BillingEditor({
  tenant,
}: {
  tenant: TenantOverviewItem;
}) {
  const qc = useQueryClient();
  const [billingType, setBillingType] = useState<string>(tenant.billing_type ?? "");
  const [billingAmount, setBillingAmount] = useState<string>(
    tenant.billing_amount !== null ? String(tenant.billing_amount) : "",
  );
  const [billingCurrency, setBillingCurrency] = useState<string>(tenant.billing_currency || "CZK");
  const [billingNote, setBillingNote] = useState<string>(tenant.billing_note ?? "");
  // Fakturační údaje příjemce
  const [companyName, setCompanyName] = useState<string>(tenant.billing_company_name ?? "");
  const [ico, setIco] = useState<string>(tenant.billing_ico ?? "");
  const [dic, setDic] = useState<string>(tenant.billing_dic ?? "");
  const [addressStreet, setAddressStreet] = useState<string>(tenant.billing_address_street ?? "");
  const [addressCity, setAddressCity] = useState<string>(tenant.billing_address_city ?? "");
  const [addressZip, setAddressZip] = useState<string>(tenant.billing_address_zip ?? "");
  const [emailRecipient, setEmailRecipient] = useState<string>(tenant.billing_email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.patch(`/admin/tenants/${tenant.id}`, {
      billing_type:     billingType || null,
      billing_amount:   billingAmount === "" ? null : parseFloat(billingAmount),
      billing_currency: billingCurrency.toUpperCase().slice(0, 3),
      billing_note:     billingNote || null,
      billing_company_name:   companyName || null,
      billing_ico:            ico || null,
      billing_dic:            dic || null,
      billing_address_street: addressStreet || null,
      billing_address_city:   addressCity || null,
      billing_address_zip:    addressZip || null,
      billing_email:          emailRecipient || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-tenant-overview"] });
      setSavedAt(new Date().toLocaleTimeString("cs-CZ"));
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  // Spočti odhad měsíčního příjmu pro tooltip
  const estimate = (() => {
    if (billingType === "per_employee" && billingAmount) {
      const amt = parseFloat(billingAmount);
      return isNaN(amt) ? null : amt * tenant.employee_count;
    }
    if (billingType === "monthly" && billingAmount) {
      return parseFloat(billingAmount) || null;
    }
    if (billingType === "yearly" && billingAmount) {
      return (parseFloat(billingAmount) || 0) / 12;
    }
    return null;
  })();

  return (
    <div className="bg-gray-50 border-t border-gray-200 px-6 py-5 space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
        <CreditCard className="h-4 w-4 text-blue-600" /> Fakturace
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor={`billing-type-${tenant.id}`}>Typ platby</Label>
          <select
            id={`billing-type-${tenant.id}`}
            value={billingType}
            onChange={(e) => setBillingType(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">— Nenastaveno —</option>
            {Object.entries(BILLING_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor={`billing-amount-${tenant.id}`}>Částka</Label>
            <Input
              id={`billing-amount-${tenant.id}`}
              type="number"
              step="0.01"
              min="0"
              value={billingAmount}
              onChange={(e) => setBillingAmount(e.target.value)}
              placeholder="např. 5000"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`billing-currency-${tenant.id}`}>Měna</Label>
            <Input
              id={`billing-currency-${tenant.id}`}
              value={billingCurrency}
              onChange={(e) => setBillingCurrency(e.target.value.toUpperCase())}
              maxLength={3}
            />
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`billing-note-${tenant.id}`}>Poznámka k fakturaci</Label>
        <textarea
          id={`billing-note-${tenant.id}`}
          value={billingNote}
          onChange={(e) => setBillingNote(e.target.value)}
          rows={2}
          placeholder="Volitelná poznámka — splatnost, kontaktní osoba, smlouva, …"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {estimate !== null && (
        <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
          <strong>Odhad měsíčního příjmu:</strong>
          {" "}{estimate.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })} {billingCurrency}
          {billingType === "per_employee" && (
            <span className="ml-1 text-blue-600">
              ({billingAmount} × {tenant.employee_count} zaměstnanců)
            </span>
          )}
        </div>
      )}

      {/* ── Fakturační údaje příjemce (na faktuře) ──────────────────────── */}
      <div className="border-t border-gray-200 pt-4 space-y-3">
        <div className="text-sm font-semibold text-gray-700">Fakturační údaje příjemce</div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`bc-name-${tenant.id}`}>Název firmy *</Label>
            <Input
              id={`bc-name-${tenant.id}`}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="např. ABC s.r.o."
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`bc-email-${tenant.id}`}>Fakturační email *</Label>
            <Input
              id={`bc-email-${tenant.id}`}
              type="email"
              value={emailRecipient}
              onChange={(e) => setEmailRecipient(e.target.value)}
              placeholder="fakturace@firma.cz"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`bc-ico-${tenant.id}`}>IČO *</Label>
            <Input
              id={`bc-ico-${tenant.id}`}
              value={ico}
              onChange={(e) => setIco(e.target.value)}
              maxLength={20}
              placeholder="12345678"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`bc-dic-${tenant.id}`}>DIČ (volitelně)</Label>
            <Input
              id={`bc-dic-${tenant.id}`}
              value={dic}
              onChange={(e) => setDic(e.target.value)}
              maxLength={20}
              placeholder="CZ12345678"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`bc-street-${tenant.id}`}>Ulice + č.p.</Label>
          <Input
            id={`bc-street-${tenant.id}`}
            value={addressStreet}
            onChange={(e) => setAddressStreet(e.target.value)}
            placeholder="Dlouhá 1"
          />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`bc-zip-${tenant.id}`}>PSČ</Label>
            <Input
              id={`bc-zip-${tenant.id}`}
              value={addressZip}
              onChange={(e) => setAddressZip(e.target.value)}
              maxLength={10}
              placeholder="110 00"
            />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor={`bc-city-${tenant.id}`}>Město</Label>
            <Input
              id={`bc-city-${tenant.id}`}
              value={addressCity}
              onChange={(e) => setAddressCity(e.target.value)}
              placeholder="Praha"
            />
          </div>
        </div>
        <div className="text-xs text-gray-500">
          Pro vystavení faktury jsou povinné: <strong>Název firmy</strong>, <strong>IČO</strong> a <strong>fakturační email</strong>.
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {savedAt && `Uloženo v ${savedAt}`}
        </span>
        <Button size="sm" onClick={() => mutation.mutate()} loading={mutation.isPending}>
          <Save className="h-3.5 w-3.5 mr-1" /> Uložit fakturaci
        </Button>
      </div>
    </div>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [expandedTenantId, setExpandedTenantId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newTenantName, setNewTenantName] = useState("");
  const [newOzoEmail, setNewOzoEmail] = useState("");
  const [newOzoFullName, setNewOzoFullName] = useState("");
  const [newExternalLogin, setNewExternalLogin] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdInfo, setCreatedInfo] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<TenantOverviewResponse>({
    queryKey: ["admin-tenant-overview"],
    queryFn: () => api.get("/admin/tenant-overview"),
    refetchInterval: 60_000,
  });

  const createTenantMutation = useMutation<
    { tenant: { id: string; name: string }; ozo_user_id: string; onboarding_email_sent_to: string },
    ApiError,
    void
  >({
    mutationFn: () => api.post("/admin/tenants", {
      tenant_name: newTenantName,
      ozo_email: newOzoEmail,
      ozo_full_name: newOzoFullName || null,
      external_login_enabled: newExternalLogin,
    }),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ["admin-tenant-overview"] });
      setCreatedInfo(
        `Zákazník "${resp.tenant.name}" vytvořen. ` +
        `OZO bude muset kliknout na link v emailu (${resp.onboarding_email_sent_to}) ` +
        `a nastavit si heslo.`,
      );
      setNewTenantName("");
      setNewOzoEmail("");
      setNewOzoFullName("");
      setNewExternalLogin(false);
      setCreateError(null);
    },
    onError: (err) => {
      setCreateError(err.detail || "Vytvoření selhalo");
      setCreatedInfo(null);
    },
  });

  const impersonateMutation = useMutation({
    mutationFn: (tenantId: string) => api.post<ImpersonateResponse>(
      "/admin/impersonate-tenant", { tenant_id: tenantId },
    ),
    onSuccess: (data) => {
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("impersonating_tenant", data.tenant_name);
      router.push("/dashboard");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  // Spočti celkový měsíční odhad příjmu
  const monthlyEstimate = (data?.tenants ?? []).reduce((sum, t) => {
    if (!t.billing_amount || !t.billing_type) return sum;
    if (t.billing_type === "monthly") return sum + t.billing_amount;
    if (t.billing_type === "yearly") return sum + t.billing_amount / 12;
    if (t.billing_type === "per_employee") return sum + t.billing_amount * t.employee_count;
    return sum;
  }, 0);

  if (isError) {
    return (
      <div>
        <Header title="Zákazníci" />
        <div className="p-6">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 inline mr-2" />
            Nemáte oprávnění platform admin.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Zákazníci"
        actions={
          <Button
            size="sm"
            onClick={() => {
              setCreateError(null);
              setCreatedInfo(null);
              setCreateOpen(true);
            }}
          >
            <Plus className="h-4 w-4 mr-1.5" /> Nový zákazník
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Souhrn */}
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Celkem zákazníků</p>
              <p className="text-3xl font-bold text-gray-900 mt-1">
                {data?.total_tenants ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Celkem zaměstnanců</p>
              <p className="text-3xl font-bold text-blue-700 mt-1">
                {data?.total_employees ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
                Odhad měsíčního příjmu
              </p>
              <p className="text-3xl font-bold text-emerald-700 mt-1">
                {monthlyEstimate.toLocaleString("cs-CZ", { maximumFractionDigits: 0 })}
                <span className="text-base font-medium text-emerald-600 ml-1">CZK</span>
              </p>
            </CardContent>
          </Card>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Tabulka zákazníků */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Načítám…
              </div>
            ) : !data || data.tenants.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Users className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádní zákazníci</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="w-8 py-3" />
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Zákazník</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Vytvořeno</th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <Users className="h-3.5 w-3.5 inline mr-1" /> Zaměstnanci
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <Briefcase className="h-3.5 w-3.5 inline mr-1" /> Pracoviště
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">
                        <GraduationCap className="h-3.5 w-3.5 inline mr-1" /> Školení
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Fakturace</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {data.tenants.map(t => {
                      const expanded = expandedTenantId === t.id;
                      return (
                        <Fragment key={t.id}>
                          <tr
                            className={cn(
                              "hover:bg-gray-50 cursor-pointer",
                              expanded && "bg-blue-50/40",
                            )}
                            onClick={() => setExpandedTenantId(expanded ? null : t.id)}
                          >
                            <td className="py-3 px-2 text-gray-400">
                              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            </td>
                            <td className="py-3 px-4 font-medium text-gray-900">
                              <div className="flex flex-col">
                                <span>{t.name}</span>
                                <span className="text-[11px] font-mono font-normal text-gray-400">
                                  {t.slug}
                                </span>
                              </div>
                              {!t.is_active && (
                                <span className="ml-2 inline-flex rounded-full bg-gray-100 text-gray-500 px-1.5 py-0.5 text-[10px] font-medium">
                                  pozastaven
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-xs text-gray-600">{formatDate(t.created_at)}</td>
                            <td className="py-3 px-4 text-right font-bold text-blue-700">{t.employee_count}</td>
                            <td className="py-3 px-4 text-right text-gray-600">{t.workplace_count}</td>
                            <td className="py-3 px-4 text-right text-gray-600">{t.training_assignment_count}</td>
                            <td className="py-3 px-4">
                              {t.billing_type ? (
                                <span className="text-xs text-gray-700">
                                  {BILLING_TYPE_LABELS[t.billing_type]}
                                  {t.billing_amount !== null && (
                                    <strong className="ml-1">
                                      {t.billing_amount.toLocaleString("cs-CZ")} {t.billing_currency}
                                    </strong>
                                  )}
                                </span>
                              ) : (
                                <span className="text-xs text-gray-400 italic">— Nenastaveno —</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
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
                          {expanded && (
                            <tr>
                              <td colSpan={8} className="p-0">
                                <div className="border-t border-gray-100 bg-gray-50/30 p-4 space-y-4">
                                  <div className="rounded-md bg-white border border-gray-200 p-4">
                                    <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700">
                                      <Globe className="h-4 w-4 text-blue-600" />
                                      Subdomain
                                    </h3>
                                    <SubdomainEditor
                                      tenantId={t.id}
                                      currentSlug={t.slug}
                                    />
                                  </div>
                                  <BillingEditor tenant={t} />
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          <strong>Tip:</strong> klikni na řádek zákazníka pro nastavení typu platby a měsíční částky.
          Při typu &bdquo;Za zaměstnance&ldquo; se odhad spočítá automaticky podle aktuálního počtu zaměstnanců.
        </div>
      </div>

      {/* ── Dialog: Vytvořit nového zákazníka ───────────────────────────── */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nový zákazník"
        size="md"
      >
        <div className="space-y-4">
          <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
            <Building2 className="h-3.5 w-3.5 inline mr-1" />
            Vytvoří se nový tenant + první OZO uživatel. OZO obdrží email
            s linkem pro nastavení hesla. Až bude přihlášen, projde 2-krokový
            onboarding wizard (firma + první pracoviště).
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new-tenant-name">Název firmy zákazníka *</Label>
            <Input
              id="new-tenant-name"
              value={newTenantName}
              onChange={(e) => setNewTenantName(e.target.value)}
              placeholder="např. Strojírny Nováček s.r.o."
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new-ozo-email">Email OZO *</Label>
            <Input
              id="new-ozo-email"
              type="email"
              value={newOzoEmail}
              onChange={(e) => setNewOzoEmail(e.target.value)}
              placeholder="ozo@firmazakaznika.cz"
            />
            <p className="text-xs text-gray-500">
              Na tuto adresu pošleme link pro nastavení hesla.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new-ozo-name">Jméno OZO (volitelně)</Label>
            <Input
              id="new-ozo-name"
              value={newOzoFullName}
              onChange={(e) => setNewOzoFullName(e.target.value)}
              placeholder="Bc. Jan Novák"
            />
          </div>

          <Label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={newExternalLogin}
              onChange={(e) => setNewExternalLogin(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-sm">
              Povolit přihlášení i HR/zaměstnancům klienta (jinak OZO-only)
            </span>
          </Label>

          {createError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              <AlertTriangle className="h-4 w-4 inline mr-1" /> {createError}
            </div>
          )}
          {createdInfo && (
            <div className="rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800">
              ✅ {createdInfo}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Zavřít
            </Button>
            <Button
              onClick={() => createTenantMutation.mutate()}
              disabled={!newTenantName || !newOzoEmail || createTenantMutation.isPending}
              loading={createTenantMutation.isPending}
            >
              Vytvořit zákazníka
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
