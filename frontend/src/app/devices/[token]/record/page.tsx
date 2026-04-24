"use client";

/**
 * QR landing stránka. Zobrazí se po naskenování QR polepu na zařízení.
 * Vyžaduje login (middleware proveruje session; pokud nepřihlášen,
 * redirect na /login s ?redirect= zpět sem).
 *
 * Přihlášený uživatel vidí:
 * - název zařízení, provozovnu, typ, datum poslední a příští revize
 * - formulář: datum (implicitně dnes) + upload PDF/obrázek + poznámka
 *
 * Submit vytvoří revision_record přes POST /revisions/{id}/records.
 * Backend sám ověří pravomoc (OZO/HR vždy, employee jen s responsibility
 * na plant_id tohoto zařízení) — při 403 zobrazí hláška.
 */

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Upload, CheckCircle2, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Revision, RevisionRecord } from "@/types/api";
import { DEVICE_TYPE_LABELS } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function getCsrf(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

async function uploadRecord(
  revisionId: string,
  performedAt: string,
  technician: string,
  notes: string,
  file: File | null,
): Promise<RevisionRecord> {
  const fd = new FormData();
  fd.append("performed_at", performedAt);
  if (technician) fd.append("technician_name", technician);
  if (notes)      fd.append("notes", notes);
  if (file)       fd.append("file", file);

  const headers: Record<string, string> = {};
  const csrf = getCsrf();
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(`/api/v1/revisions/${revisionId}/records`, {
    method: "POST",
    body: fd,
    headers,
    credentials: "same-origin",
  });
  if (res.status === 401) {
    const back = encodeURIComponent(window.location.pathname);
    window.location.href = `/login?redirect=${back}`;
    throw new ApiError(401, "Neautorizovaný přístup");
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (typeof err.detail === "string") detail = err.detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export default function DeviceQrLandingPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();

  const [performedAt, setPerformedAt] = useState(() =>
    new Date().toISOString().slice(0, 10)
  );
  const [technician, setTechnician] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const { data: revision, isLoading, error: loadError } = useQuery<Revision>({
    queryKey: ["revision-by-qr", params.token],
    queryFn: () => api.get(`/revisions/qr/${params.token}`),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="text-gray-400">Načítám…</div>
      </div>
    );
  }

  if (loadError || !revision) {
    const needsLogin = loadError instanceof ApiError && loadError.status === 401;
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-600">
              <XCircle className="h-5 w-5" />
              {needsLogin ? "Potřeba přihlášení" : "Zařízení nenalezeno"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-600">
              {needsLogin
                ? "Pro zaznamenání revize se prosím přihlaste."
                : "QR kód je neplatný nebo zařízení bylo archivováno."}
            </p>
            <Button
              onClick={() => {
                const back = encodeURIComponent(window.location.pathname);
                router.push(`/login?redirect=${back}`);
              }}
            >
              Přihlásit se
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  async function handleSubmit() {
    if (!revision) return;
    setSubmitting(true);
    setError(null);
    try {
      await uploadRecord(revision.id, performedAt, technician, notes, file);
      setSuccess(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Chyba serveru");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-600">
              <CheckCircle2 className="h-6 w-6" />
              Revize zaznamenána
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-700">
              Záznam o revizi pro <strong>{revision.title}</strong> byl uložen.
            </p>
            <div className="flex gap-2">
              <Link href="/dashboard" className="flex-1">
                <Button className="w-full" variant="outline">Domů</Button>
              </Link>
              <Button className="flex-1" onClick={() => { setSuccess(false); setFile(null); }}>
                Další záznam
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6">
      <div className="max-w-xl mx-auto space-y-4">
        <Link href="/dashboard" className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-4 w-4 mr-1" />
          Domů
        </Link>

        <Card>
          <CardHeader>
            <CardTitle>{revision.title}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-gray-600 space-y-1">
            <div>
              <strong className="text-gray-900">Provozovna:</strong> {revision.plant_name || "—"}
            </div>
            <div>
              <strong className="text-gray-900">Typ:</strong>{" "}
              {revision.device_type ? DEVICE_TYPE_LABELS[revision.device_type] : "—"}
            </div>
            {revision.device_code && (
              <div><strong className="text-gray-900">ID zařízení:</strong> {revision.device_code}</div>
            )}
            <div>
              <strong className="text-gray-900">Poslední revize:</strong>{" "}
              {revision.last_revised_at
                ? new Date(revision.last_revised_at).toLocaleDateString("cs-CZ")
                : "—"}
            </div>
            <div>
              <strong className="text-gray-900">Další revize:</strong>{" "}
              {revision.next_revision_at
                ? new Date(revision.next_revision_at).toLocaleDateString("cs-CZ")
                : "—"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Zaznamenat provedenou revizi</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="performed_at">Datum revize *</Label>
              <Input
                id="performed_at"
                type="date"
                value={performedAt}
                onChange={(e) => setPerformedAt(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="technician">Revizní technik</Label>
              <Input
                id="technician"
                value={technician}
                onChange={(e) => setTechnician(e.target.value)}
                placeholder={revision.technician_name || ""}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="notes">Poznámka</Label>
              <textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="file">Revizní zpráva (PDF nebo foto) *</Label>
              <input
                id="file"
                type="file"
                accept="application/pdf,image/*,.heic"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-blue-600 hover:file:bg-blue-100"
              />
              <p className="text-xs text-gray-400">Max 5 MB</p>
            </div>

            {error && (
              <div className={cn(
                "rounded-md px-3 py-2 text-sm",
                "bg-red-50 border border-red-200 text-red-700"
              )}>
                {error}
              </div>
            )}

            <Button
              onClick={handleSubmit}
              loading={submitting}
              disabled={!performedAt}
              className="w-full"
            >
              <Upload className="h-4 w-4 mr-1.5" />
              Odeslat
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
