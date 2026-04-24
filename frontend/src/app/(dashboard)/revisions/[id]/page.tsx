"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Download, FileText, Image as ImageIcon,
  QrCode, Upload, Trash2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Revision, RevisionRecord } from "@/types/api";
import { DEVICE_TYPE_LABELS } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const DUE_COLORS: Record<string, string> = {
  ok:          "bg-green-100 text-green-700",
  due_soon:    "bg-amber-100 text-amber-700",
  overdue:     "bg-red-100 text-red-700",
  no_schedule: "bg-gray-100 text-gray-500",
};

const DUE_LABELS: Record<string, string> = {
  ok:          "V pořádku",
  due_soon:    "Blíží se",
  overdue:     "PO TERMÍNU",
  no_schedule: "Bez termínu",
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("cs-CZ");
}

function getCsrf(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/** Multipart upload s libovolnými form fieldy (nejen file). */
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
    window.location.href = "/login";
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

export default function RevisionDetailPage() {
  const params = useParams<{ id: string }>();
  const qc = useQueryClient();
  const id = params.id;

  const [performedAt, setPerformedAt] = useState(() =>
    new Date().toISOString().slice(0, 10)
  );
  const [technician, setTechnician] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: revision, isLoading } = useQuery<Revision>({
    queryKey: ["revision", id],
    queryFn: () => api.get(`/revisions/${id}`),
  });

  const { data: records = [] } = useQuery<RevisionRecord[]>({
    queryKey: ["revision-records", id],
    queryFn: () => api.get(`/revisions/${id}/records`),
    enabled: !!id,
  });

  const uploadMutation = useMutation({
    mutationFn: () => uploadRecord(id, performedAt, technician, notes, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["revision-records", id] });
      qc.invalidateQueries({ queryKey: ["revision", id] });
      qc.invalidateQueries({ queryKey: ["revisions"] });
      setTechnician("");
      setNotes("");
      setFile(null);
      setUploadError(null);
      // reset file input
      const input = document.getElementById("record_file") as HTMLInputElement | null;
      if (input) input.value = "";
    },
    onError: (err) => setUploadError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteRecordMutation = useMutation({
    mutationFn: (rid: string) => api.delete(`/revisions/records/${rid}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["revision-records", id] });
      qc.invalidateQueries({ queryKey: ["revision", id] });
    },
  });

  if (isLoading || !revision) {
    return (
      <div>
        <Header title="Načítám…" />
        <div className="p-6"><div className="h-32 animate-pulse bg-gray-50 rounded" /></div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title={revision.title}
        actions={
          <div className="flex items-center gap-2">
            <Link href="/revisions">
              <Button variant="outline" size="sm">
                <ArrowLeft className="h-3.5 w-3.5 mr-1" />
                Zpět
              </Button>
            </Link>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(`/api/v1/revisions/${id}/qr.png`, "_blank")}
            >
              <QrCode className="h-3.5 w-3.5 mr-1" />
              Stáhnout QR
            </Button>
          </div>
        }
      />

      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Info karta ─────────────────────────────────────────────── */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Informace o zařízení</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-3">
            <InfoRow label="Provozovna" value={revision.plant_name || "—"} />
            <InfoRow label="Typ" value={revision.device_type ? DEVICE_TYPE_LABELS[revision.device_type] : "—"} />
            <InfoRow label="ID zařízení" value={revision.device_code || "—"} />
            <InfoRow label="Umístění" value={revision.location || "—"} />
            <InfoRow label="Posl. revize" value={formatDate(revision.last_revised_at)} />
            <InfoRow label="Periodicita" value={revision.valid_months ? `${revision.valid_months} měs.` : "—"} />
            <InfoRow
              label="Další revize"
              value={
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  DUE_COLORS[revision.due_status] || "bg-gray-100 text-gray-500"
                )}>
                  {formatDate(revision.next_revision_at)} · {DUE_LABELS[revision.due_status] || revision.due_status}
                </span>
              }
            />

            <div className="border-t border-gray-100 pt-3 mt-3 space-y-1">
              <div className="text-xs font-medium text-gray-500">Revizní technik</div>
              <div>{revision.technician_name || "—"}</div>
              {revision.technician_email && (
                <a className="block text-blue-600 hover:underline" href={`mailto:${revision.technician_email}`}>
                  {revision.technician_email}
                </a>
              )}
              {revision.technician_phone && (
                <a className="block text-blue-600 hover:underline" href={`tel:${revision.technician_phone}`}>
                  {revision.technician_phone}
                </a>
              )}
            </div>

            {revision.notes && (
              <div className="border-t border-gray-100 pt-3 mt-3">
                <div className="text-xs font-medium text-gray-500 mb-1">Poznámky</div>
                <div className="whitespace-pre-wrap">{revision.notes}</div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Upload + Timeline ──────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-6">
          {/* Upload form */}
          <Card>
            <CardHeader>
              <CardTitle>Zaznamenat provedenou revizi</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
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
                  <Label htmlFor="technician_name">Revizní technik</Label>
                  <Input
                    id="technician_name"
                    value={technician}
                    onChange={(e) => setTechnician(e.target.value)}
                    placeholder={revision.technician_name || ""}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="record_notes">Poznámka</Label>
                <textarea
                  id="record_notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="record_file">Revizní zpráva (PDF nebo foto)</Label>
                <input
                  id="record_file"
                  type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp,image/heic"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-blue-600 hover:file:bg-blue-100"
                />
                <p className="text-xs text-gray-400">Max 5 MB · PDF, PNG, JPG, WEBP, HEIC</p>
              </div>

              {uploadError && (
                <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  {uploadError}
                </div>
              )}

              <div className="flex justify-end">
                <Button
                  onClick={() => uploadMutation.mutate()}
                  loading={uploadMutation.isPending}
                  disabled={!performedAt}
                >
                  <Upload className="h-4 w-4 mr-1.5" />
                  Uložit záznam
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Timeline */}
          <Card>
            <CardHeader>
              <CardTitle>Historie revizí ({records.length})</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {records.length === 0 ? (
                <div className="text-sm text-gray-400 py-8 text-center">
                  Zatím žádný zaznamenaný záznam.
                </div>
              ) : (
                <ul className="divide-y divide-gray-100">
                  {records.map((r) => (
                    <li key={r.id} className="px-4 py-3 flex items-start gap-3">
                      <div className="text-gray-400 pt-0.5">
                        {r.pdf_path ? <FileText className="h-5 w-5" /> : <ImageIcon className="h-5 w-5" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">
                            {formatDate(r.performed_at)}
                          </span>
                          {r.technician_name && (
                            <span className="text-xs text-gray-500">{r.technician_name}</span>
                          )}
                        </div>
                        {r.notes && (
                          <div className="text-sm text-gray-600 mt-0.5 whitespace-pre-wrap">
                            {r.notes}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {(r.pdf_path || r.image_path) && (
                          <button
                            onClick={() => window.open(`/api/v1/revisions/records/${r.id}/file`, "_blank")}
                            className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                            title="Otevřít přílohu"
                          >
                            <Download className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          onClick={() => {
                            if (confirm("Smazat tento záznam?"))
                              deleteRecordMutation.mutate(r.id);
                          }}
                          className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                          title="Smazat"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="text-xs text-gray-500 pt-0.5">{label}</span>
      <span className="text-right font-medium text-gray-900">{value}</span>
    </div>
  );
}
