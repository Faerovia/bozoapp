"use client";

/**
 * QR scan stránka pro provozní deník.
 *
 * Flow:
 *   1. Uživatel naskenuje QR kód na zařízení (mobil)
 *   2. Otevře /devices/{qr_token}/operating-log
 *   3. Pokud není přihlášen → redirect /login?next=...
 *   4. Načte zařízení přes /api/v1/operating-logs/qr/{token}
 *   5. Zobrazí formulář pro nový zápis (3-way kapacita) + auto-fill jména/data
 *   6. Po uložení redirect na /operating-logs
 */

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, BookOpenCheck,
  CheckCircle2, XCircle, Loader2, ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  OperatingLogDevice, CapabilityStatus,
} from "@/types/api";
import {
  DEVICE_CATEGORY_LABELS, OPERATING_PERIOD_LABELS,
} from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface AuthMe {
  id: string;
  email: string;
  full_name: string | null;
}

export default function OperatingLogScanPage(
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = use(params);
  const router = useRouter();
  const qc = useQueryClient();

  const [performedAt, setPerformedAt] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [performedByName, setPerformedByName] = useState("");
  const [capable, setCapable] = useState<CapabilityStatus[]>([]);
  const [overall, setOverall] = useState<CapabilityStatus>("yes");
  const [notes, setNotes] = useState("");
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const { data: me } = useQuery<AuthMe>({
    queryKey: ["auth", "me"],
    queryFn: () => api.get("/auth/me"),
    retry: false,
    staleTime: 10 * 60 * 1000,
  });

  const { data: device, isLoading, isError, error } = useQuery<OperatingLogDevice>({
    queryKey: ["operating-log-by-qr", token],
    queryFn: () => api.get(`/operating-logs/qr/${encodeURIComponent(token)}`),
    enabled: !!me,
    retry: false,
  });

  // Po načtení device naplň pole capable_items na "yes"
  useEffect(() => {
    if (device && capable.length === 0) {
      setCapable(device.check_items.map(() => "yes" as CapabilityStatus));
    }
  }, [device, capable.length]);

  // Auto-fill jména
  useEffect(() => {
    if (me && !performedByName) {
      const auto = me.full_name?.trim() || me.email;
      if (auto) setPerformedByName(auto);
    }
  }, [me, performedByName]);

  const createEntry = useMutation({
    mutationFn: () =>
      api.post(`/operating-logs/devices/${device!.id}/entries`, {
        performed_at: performedAt,
        performed_by_name: performedByName,
        capable_items: capable,
        overall_status: overall,
        notes: notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["operating-logs"] });
      setSubmitted(true);
    },
    onError: (err) =>
      setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function setItem(i: number, v: CapabilityStatus) {
    setCapable((arr) => arr.map((x, idx) => (idx === i ? v : x)));
    if (v === "no" && overall !== "no") setOverall("no");
    else if (v === "conditional" && overall === "yes") setOverall("conditional");
  }

  // Auth fail → /login
  useEffect(() => {
    if (me === undefined) return;  // ještě se načítá
    if (!me) router.push(
      `/login?next=${encodeURIComponent(`/devices/${token}/operating-log`)}`,
    );
  }, [me, router, token]);

  if (!me) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }

  if (isError || !device) {
    const detail = error instanceof ApiError ? error.detail : "Zařízení nenalezeno";
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center space-y-3">
            <AlertTriangle className="h-10 w-10 mx-auto text-amber-500" />
            <h1 className="text-lg font-semibold text-gray-900">
              Zařízení nenalezeno
            </h1>
            <p className="text-sm text-gray-600">
              {detail}
            </p>
            <p className="text-xs text-gray-400">
              QR kód patří jinému tenantu nebo bylo zařízení smazáno.
            </p>
            <Button variant="outline" onClick={() => router.push("/operating-logs")}>
              <ArrowLeft className="h-4 w-4 mr-1.5" />
              Zpět na deníky
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center space-y-4">
            <ShieldCheck className="h-12 w-12 mx-auto text-green-500" />
            <h1 className="text-lg font-semibold text-gray-900">
              Zápis uložen
            </h1>
            <p className="text-sm text-gray-600">
              Zařízení <strong>{device.title}</strong> — souhrn{" "}
              <strong>
                {overall === "yes" ? "ANO" :
                 overall === "conditional" ? "Podmíněný" : "NE"}
              </strong>.
            </p>
            {overall !== "yes" && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                Alert email byl odeslán zodpovědným osobám provozovny.
              </p>
            )}
            <div className="flex gap-2 justify-center pt-2">
              <Button onClick={() => {
                setSubmitted(false);
                setNotes("");
                setCapable(device.check_items.map(() => "yes" as CapabilityStatus));
                setOverall("yes");
              }}>
                Další zápis
              </Button>
              <Button variant="outline" onClick={() => router.push("/operating-logs")}>
                Hotovo
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const itemBtnCls = (active: boolean, color: "green" | "amber" | "red") => cn(
    "flex-1 rounded-md px-2 py-2 text-xs font-medium border transition-colors",
    active && color === "green" && "bg-green-100 border-green-300 text-green-700",
    active && color === "amber" && "bg-amber-100 border-amber-300 text-amber-700",
    active && color === "red" && "bg-red-100 border-red-300 text-red-700",
    !active && "bg-white border-gray-200 text-gray-400",
  );

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-xl mx-auto space-y-4">
        {/* Hlavička */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase text-gray-400 font-medium">
                  {DEVICE_CATEGORY_LABELS[device.category]}
                </p>
                <h1 className="text-lg font-semibold text-gray-900 mt-0.5">
                  {device.title}
                </h1>
                {device.device_code && (
                  <p className="text-xs text-gray-500">Kód: {device.device_code}</p>
                )}
                {device.location && (
                  <p className="text-xs text-gray-500">{device.location}</p>
                )}
                <p className="text-xs text-gray-400 mt-1">
                  Periodicita: {OPERATING_PERIOD_LABELS[device.period]}
                  {device.period_note && ` · ${device.period_note}`}
                </p>
              </div>
              <div className="rounded-md bg-blue-100 p-2 text-blue-600 shrink-0">
                <BookOpenCheck className="h-5 w-5" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Formulář */}
        <Card>
          <CardContent className="p-4 space-y-4">
            <h2 className="text-sm font-semibold text-gray-700">Nový zápis</h2>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="performed_at">Datum kontroly *</Label>
                <Input
                  id="performed_at"
                  type="date"
                  value={performedAt}
                  onChange={(e) => setPerformedAt(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="performed_by_name">Kontroloval *</Label>
                <Input
                  id="performed_by_name"
                  value={performedByName}
                  onChange={(e) => setPerformedByName(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="rounded-md border border-gray-200 p-3 space-y-2">
              <div className="flex items-center justify-between border-b border-gray-100 pb-1">
                <Label>Kontrolní úkony</Label>
                <span className="text-[10px] uppercase text-gray-500 font-medium">
                  Způsobilý
                </span>
              </div>
              {device.check_items.map((item, i) => (
                <div key={i} className="space-y-1 py-1 border-b border-gray-100 last:border-b-0">
                  <p className="text-sm text-gray-700">
                    <span className="text-gray-400 mr-1">{i + 1}.</span>
                    {item}
                  </p>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => setItem(i, "yes")}
                      className={itemBtnCls(capable[i] === "yes", "green")}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 inline mr-1" /> ANO
                    </button>
                    <button
                      type="button"
                      onClick={() => setItem(i, "conditional")}
                      className={itemBtnCls(capable[i] === "conditional", "amber")}
                    >
                      <AlertTriangle className="h-3.5 w-3.5 inline mr-1" /> Podm.
                    </button>
                    <button
                      type="button"
                      onClick={() => setItem(i, "no")}
                      className={itemBtnCls(capable[i] === "no", "red")}
                    >
                      <XCircle className="h-3.5 w-3.5 inline mr-1" /> NE
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 space-y-2">
              <p className="text-sm font-medium text-amber-900">Souhrn — způsobilost k provozu</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setOverall("yes")}
                  className={cn(
                    "flex-1 rounded-md px-3 py-2 text-sm font-medium border",
                    overall === "yes"
                      ? "bg-green-600 text-white border-green-600"
                      : "bg-white border-gray-300 text-gray-600",
                  )}
                >ANO</button>
                <button
                  type="button"
                  onClick={() => setOverall("conditional")}
                  className={cn(
                    "flex-1 rounded-md px-3 py-2 text-sm font-medium border",
                    overall === "conditional"
                      ? "bg-amber-600 text-white border-amber-600"
                      : "bg-white border-gray-300 text-gray-600",
                  )}
                >Podmíněný</button>
                <button
                  type="button"
                  onClick={() => setOverall("no")}
                  className={cn(
                    "flex-1 rounded-md px-3 py-2 text-sm font-medium border",
                    overall === "no"
                      ? "bg-red-600 text-white border-red-600"
                      : "bg-white border-gray-300 text-gray-600",
                  )}
                >NE</button>
              </div>
              {overall !== "yes" && (
                <p className="text-xs text-amber-800 italic">
                  ⚠ Po uložení se automaticky odešle alert email zodpovědným osobám.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="entry-notes">Poznámky / problémy</Label>
              <textarea
                id="entry-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>

            {serverError && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {serverError}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <Button
                variant="outline"
                onClick={() => router.push("/operating-logs")}
                className="flex-1"
              >
                Zrušit
              </Button>
              <Button
                onClick={() => createEntry.mutate()}
                loading={createEntry.isPending}
                className="flex-1"
              >
                Uložit zápis
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
