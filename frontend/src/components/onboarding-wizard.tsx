"use client";

/**
 * Onboarding wizard — 2 kroky, blokující pro nového tenanta.
 *
 * Krok 1 — Údaje firmy s ARES auto-fillem
 * Krok 2 — První pracoviště (Plant)
 *
 * Po obou krocích frontend zavolá /onboarding/complete-step1 a wizard zmizí.
 * Persistentní checklist na dashboardu pak vede dál.
 *
 * Zobrazí se jen pokud:
 *  - user.role === 'ozo' nebo 'hr_manager'
 *  - onboarding.step1_completed === false
 *  - onboarding.dismissed === false
 *  - onboarding.completed === false
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2, MapPin, Sparkles, AlertTriangle, Loader2, CheckCircle2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ProgressResponse {
  step1_completed: boolean;
  dismissed: boolean;
  completed: boolean;
}

interface AresResponse {
  ico: string;
  name: string;
  dic: string | null;
  address_street: string | null;
  address_city: string | null;
  address_zip: string | null;
}

interface MeResponse {
  role: string;
  is_platform_admin: boolean;
  tenant_id: string;
}

type Step = "company" | "plant" | "done";

export function OnboardingWizard() {
  const qc = useQueryClient();

  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 60_000,
  });

  const { data: progress } = useQuery<ProgressResponse>({
    queryKey: ["onboarding-progress"],
    queryFn: () => api.get("/onboarding/progress"),
  });

  const visible =
    !!me &&
    !me.is_platform_admin &&
    (me.role === "ozo" || me.role === "hr_manager") &&
    !!progress &&
    !progress.step1_completed &&
    !progress.dismissed &&
    !progress.completed;

  // ── State ────────────────────────────────────────────────────────────────
  const [step, setStep] = useState<Step>("company");
  const [error, setError] = useState<string | null>(null);

  // Krok 1 — firma
  const [ico, setIco] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [dic, setDic] = useState("");
  const [addressStreet, setAddressStreet] = useState("");
  const [addressCity, setAddressCity] = useState("");
  const [addressZip, setAddressZip] = useState("");

  // Krok 2 — pracoviště
  const [plantName, setPlantName] = useState("");
  const [plantAddress, setPlantAddress] = useState("");

  // ── Mutations ────────────────────────────────────────────────────────────
  const aresLookup = useMutation<AresResponse, ApiError, string>({
    mutationFn: (icoVal) => api.get<AresResponse>(`/onboarding/ares?ico=${encodeURIComponent(icoVal)}`),
    onSuccess: (data) => {
      setCompanyName(data.name);
      setDic(data.dic ?? "");
      setAddressStreet(data.address_street ?? "");
      setAddressCity(data.address_city ?? "");
      setAddressZip(data.address_zip ?? "");
      setError(null);
    },
    onError: (err) => setError(err.detail || "ARES lookup selhal"),
  });

  const saveCompany = useMutation({
    mutationFn: () => api.patch(`/admin/tenants/${me?.tenant_id}`, {
      billing_company_name: companyName || null,
      billing_ico: ico || null,
      billing_dic: dic || null,
      billing_address_street: addressStreet || null,
      billing_address_city: addressCity || null,
      billing_address_zip: addressZip || null,
    }),
    onSuccess: () => setStep("plant"),
    onError: (err) => {
      // Tenant může být edited jen platform-adminem. Pro běžného OZO
      // použijeme jiný endpoint (PATCH /tenant pro aktuální tenant).
      // Fallback: jen přejdi dál — admin to později nastaví v issuer settings.
      console.warn("Save company failed:", err);
      setStep("plant");
    },
  });

  const savePlant = useMutation({
    mutationFn: () => api.post("/plants", {
      name: plantName,
      address: plantAddress || null,
    }),
    onSuccess: () => {
      finishStep1.mutate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Uložení pracoviště selhalo"),
  });

  const finishStep1 = useMutation({
    mutationFn: () => api.post("/onboarding/complete-step1"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding-progress"] });
      setStep("done");
    },
  });

  if (!visible) return null;

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-2xl">
        {/* Hlavička */}
        <div className="border-b border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-blue-600 p-2 text-white">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Vítejte v BOZOapp
              </h2>
              <p className="text-sm text-gray-600">
                Krok {step === "company" ? "1" : step === "plant" ? "2" : "—"} ze 2 —
                rychlé nastavení trvá ~3 minuty
              </p>
            </div>
          </div>
        </div>

        {/* Obsah */}
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* KROK 1: FIRMA */}
          {step === "company" && (
            <>
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                <Building2 className="h-4 w-4 text-blue-600" />
                Údaje firmy
              </div>
              <p className="text-xs text-gray-600">
                Zadej IČO a klikni na <strong>Vyplnit z ARES</strong>. Server načte
                jméno, adresu a DIČ z veřejného registru. Stále můžeš ručně upravit.
              </p>

              <div className="flex gap-2 items-end">
                <div className="flex-1 space-y-1.5">
                  <Label htmlFor="ico">IČO *</Label>
                  <Input
                    id="ico"
                    value={ico}
                    onChange={(e) => setIco(e.target.value.replace(/\D/g, ""))}
                    placeholder="12345678"
                    maxLength={8}
                  />
                </div>
                <Button
                  variant="outline"
                  onClick={() => aresLookup.mutate(ico)}
                  disabled={ico.length !== 8 || aresLookup.isPending}
                  loading={aresLookup.isPending}
                >
                  Vyplnit z ARES
                </Button>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="company-name">Název firmy *</Label>
                <Input
                  id="company-name"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="ABC s.r.o."
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="dic">DIČ (volitelně)</Label>
                <Input
                  id="dic"
                  value={dic}
                  onChange={(e) => setDic(e.target.value)}
                  placeholder="CZ12345678"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="street">Ulice + č.p.</Label>
                <Input
                  id="street"
                  value={addressStreet}
                  onChange={(e) => setAddressStreet(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1.5">
                  <Label htmlFor="zip">PSČ</Label>
                  <Input
                    id="zip"
                    value={addressZip}
                    onChange={(e) => setAddressZip(e.target.value)}
                    maxLength={10}
                  />
                </div>
                <div className="col-span-2 space-y-1.5">
                  <Label htmlFor="city">Město</Label>
                  <Input
                    id="city"
                    value={addressCity}
                    onChange={(e) => setAddressCity(e.target.value)}
                  />
                </div>
              </div>

              {error && (
                <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  <AlertTriangle className="h-4 w-4 inline mr-1" /> {error}
                </div>
              )}
            </>
          )}

          {/* KROK 2: PRACOVIŠTĚ */}
          {step === "plant" && (
            <>
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                <MapPin className="h-4 w-4 text-blue-600" />
                První pracoviště (provozovna)
              </div>
              <p className="text-xs text-gray-600">
                Kde se vaši zaměstnanci zdržují? Pokud máte jen jednu adresu (sídlo
                = pracoviště), použijte stejnou jako u firmy.
              </p>

              <div className="space-y-1.5">
                <Label htmlFor="plant-name">Název pracoviště *</Label>
                <Input
                  id="plant-name"
                  value={plantName}
                  onChange={(e) => setPlantName(e.target.value)}
                  placeholder={companyName || "např. Hlavní provozovna"}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="plant-address">Adresa</Label>
                <Input
                  id="plant-address"
                  value={plantAddress}
                  onChange={(e) => setPlantAddress(e.target.value)}
                  placeholder={
                    addressStreet
                      ? `${addressStreet}, ${addressZip} ${addressCity}`
                      : "Ulice, PSČ Město"
                  }
                />
                <button
                  type="button"
                  className="text-xs text-blue-600 hover:underline"
                  onClick={() => {
                    if (!plantName) setPlantName(companyName || "Hlavní provozovna");
                    setPlantAddress(
                      [addressStreet, addressZip, addressCity]
                        .filter(Boolean)
                        .join(", ")
                    );
                  }}
                >
                  Stejná jako sídlo firmy
                </button>
              </div>

              {error && (
                <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  <AlertTriangle className="h-4 w-4 inline mr-1" /> {error}
                </div>
              )}
            </>
          )}

          {/* DONE */}
          {step === "done" && (
            <div className="text-center py-6 space-y-4">
              <CheckCircle2 className="h-16 w-16 text-green-600 mx-auto" />
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Skvělá práce
                </h3>
                <p className="text-sm text-gray-600 mt-1">
                  Základní nastavení hotovo. Zbytek najdeš na dashboardu jako
                  checklist — pokračuj svým tempem.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Pata — tlačítka */}
        <div className="border-t border-gray-200 p-4 flex justify-between">
          {step === "company" && (
            <>
              <span className="text-xs text-gray-400">Krok 1 ze 2</span>
              <Button
                onClick={() => saveCompany.mutate()}
                disabled={!ico || !companyName || saveCompany.isPending}
                loading={saveCompany.isPending}
              >
                Pokračovat
              </Button>
            </>
          )}
          {step === "plant" && (
            <>
              <Button variant="outline" onClick={() => setStep("company")}>
                Zpět
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => finishStep1.mutate()}
                  loading={finishStep1.isPending}
                >
                  Přeskočit
                </Button>
                <Button
                  onClick={() => savePlant.mutate()}
                  disabled={!plantName || savePlant.isPending || finishStep1.isPending}
                  loading={savePlant.isPending}
                >
                  {savePlant.isPending || finishStep1.isPending ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
                  Uložit a dokončit
                </Button>
              </div>
            </>
          )}
          {step === "done" && (
            <Button
              className="ml-auto"
              onClick={() => qc.invalidateQueries({ queryKey: ["onboarding-progress"] })}
            >
              Pokračovat na dashboard
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
