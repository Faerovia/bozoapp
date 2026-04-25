"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Trash2, Camera, ListTodo, Loader2, Upload, Download, Lock, FileSignature,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AccidentReport } from "@/types/api";

const MAX_PHOTOS = 2;

const ACTION_STATUS_LABELS: Record<string, string> = {
  pending:     "Čeká",
  in_progress: "Probíhá",
  done:        "Hotovo",
  cancelled:   "Zrušeno",
};

const ACTION_STATUS_COLORS: Record<string, string> = {
  pending:     "bg-amber-100 text-amber-700",
  in_progress: "bg-blue-100 text-blue-700",
  done:        "bg-green-100 text-green-700",
  cancelled:   "bg-gray-100 text-gray-500",
};

interface ActionItem {
  id: string;
  accident_report_id: string;
  title: string;
  description: string | null;
  status: "pending" | "in_progress" | "done" | "cancelled";
  due_date: string | null;
  assigned_to: string | null;
  completed_at: string | null;
  is_default: boolean;
  sort_order: number;
  created_at: string;
}

interface PhotoItem {
  id: string;
  accident_report_id: string;
  photo_path: string;
  caption: string | null;
  created_at: string;
}

// ── Akční plán ───────────────────────────────────────────────────────────────

function ActionPlanSection({
  accidentId,
  reportStatus,
}: {
  accidentId: string;
  reportStatus: "draft" | "final" | "archived";
}) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newDueDate, setNewDueDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: items = [], isLoading } = useQuery<ActionItem[]>({
    queryKey: ["accident-action-items", accidentId],
    queryFn: () => api.get(`/accident-reports/${accidentId}/action-items`),
  });

  const createMutation = useMutation({
    mutationFn: (payload: { title: string; description: string | null; due_date: string | null }) =>
      api.post(`/accident-reports/${accidentId}/action-items`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-action-items", accidentId] });
      setAdding(false);
      setNewTitle("");
      setNewDescription("");
      setNewDueDate("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ActionItem> }) =>
      api.patch(`/accident-action-items/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accident-action-items", accidentId] }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/accident-action-items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accident-action-items", accidentId] }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const canEdit = reportStatus !== "archived";

  function handleAdd() {
    if (!newTitle.trim()) {
      setError("Zadejte název položky");
      return;
    }
    createMutation.mutate({
      title: newTitle.trim(),
      description: newDescription.trim() || null,
      due_date: newDueDate || null,
    });
  }

  function formatDate(iso: string | null) {
    if (!iso) return null;
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <ListTodo className="h-4 w-4 text-blue-600" />
          Akční plán
        </h3>
        {canEdit && !adding && (
          <Button size="sm" variant="outline" onClick={() => { setAdding(true); setError(null); }}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Nová položka
          </Button>
        )}
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {adding && (
        <div className="space-y-2 rounded-md border border-blue-200 bg-blue-50/40 p-3">
          <div className="space-y-1.5">
            <Label htmlFor="new-title" className="text-xs">Název *</Label>
            <Input
              id="new-title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="např. Doplnit krycí mřížku"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-desc" className="text-xs">Popis</Label>
            <textarea
              id="new-desc"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-due" className="text-xs">Termín</Label>
            <Input id="new-due" type="date" value={newDueDate} onChange={(e) => setNewDueDate(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button size="sm" variant="ghost" onClick={() => { setAdding(false); setError(null); }}>
              Zrušit
            </Button>
            <Button size="sm" onClick={handleAdd} loading={createMutation.isPending}>
              Přidat
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-gray-400 py-4">
          <Loader2 className="h-4 w-4 animate-spin" /> Načítám…
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-gray-400 italic py-2">
          Akční plán bude vytvořen po finalizaci nahlášení.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className={cn(
                "rounded-md border bg-white px-3 py-2.5 transition-colors",
                item.is_default ? "border-blue-200 bg-blue-50/20" : "border-gray-200"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-900">{item.title}</span>
                    {item.is_default && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-[10px] font-medium">
                        <Lock className="h-2.5 w-2.5" /> Výchozí
                      </span>
                    )}
                  </div>
                  {item.description && (
                    <p className="text-xs text-gray-600 mt-1 whitespace-pre-wrap">{item.description}</p>
                  )}
                  {item.due_date && (
                    <p className="text-xs text-gray-500 mt-1">
                      Termín: <span className="font-medium">{formatDate(item.due_date)}</span>
                    </p>
                  )}
                  {item.completed_at && (
                    <p className="text-xs text-green-700 mt-1">
                      Splněno: {formatDate(item.completed_at)}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <select
                    value={item.status}
                    onChange={(e) => updateMutation.mutate({
                      id: item.id,
                      data: { status: e.target.value as ActionItem["status"] },
                    })}
                    disabled={!canEdit}
                    className={cn(
                      "rounded-full px-2 py-1 text-[11px] font-medium border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed",
                      ACTION_STATUS_COLORS[item.status],
                    )}
                  >
                    {Object.entries(ACTION_STATUS_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  {canEdit && !item.is_default && (
                    <Tooltip label="Smazat položku akčního plánu">
                      <button
                        onClick={() => {
                          if (confirm("Opravdu smazat tuto položku?"))
                            deleteMutation.mutate(item.id);
                        }}
                        className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                        aria-label="Smazat"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </Tooltip>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Fotky ────────────────────────────────────────────────────────────────────

function PhotosSection({
  accidentId,
  reportStatus,
}: {
  accidentId: string;
  reportStatus: "draft" | "final" | "archived";
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [caption, setCaption] = useState("");

  const { data: photos = [], isLoading } = useQuery<PhotoItem[]>({
    queryKey: ["accident-photos", accidentId],
    queryFn: () => api.get(`/accident-reports/${accidentId}/photos`),
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      // uploadFile podporuje jen jeden field. Caption pošleme přes ručně sestavený FormData.
      const formData = new FormData();
      formData.append("file", file);
      if (caption.trim()) formData.append("caption", caption.trim());

      // Použijeme custom fetch s CSRF tokenem
      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;
      const headers: Record<string, string> = {};
      if (csrf) headers["X-CSRF-Token"] = csrf;

      const res = await fetch(`/api/v1/accident-reports/${accidentId}/photos`, {
        method: "POST",
        headers,
        body: formData,
        credentials: "same-origin",
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const err = await res.json();
          if (typeof err.detail === "string") detail = err.detail;
        } catch {}
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-photos", accidentId] });
      setCaption("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba uploadu"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/accident-photos/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accident-photos", accidentId] }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const canEdit = reportStatus !== "archived";
  const canUpload = canEdit && photos.length < MAX_PHOTOS;

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    uploadMutation.mutate(file);
    e.target.value = "";  // reset, aby šlo nahrát stejný soubor znova
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <Camera className="h-4 w-4 text-blue-600" />
          Fotodokumentace
          <span className="text-xs font-normal text-gray-400">
            ({photos.length}/{MAX_PHOTOS})
          </span>
        </h3>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {canUpload && (
        <div className="space-y-2 rounded-md border border-dashed border-gray-300 p-3">
          <div className="space-y-1.5">
            <Label htmlFor="photo-caption" className="text-xs">Popisek (volitelný)</Label>
            <Input
              id="photo-caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="např. místo pádu, poškozené zařízení"
            />
          </div>
          <label className="flex items-center justify-center gap-2 cursor-pointer rounded-md border border-blue-300 bg-blue-50 hover:bg-blue-100 transition-colors px-3 py-2 text-sm font-medium text-blue-700">
            <Upload className="h-4 w-4" />
            {uploadMutation.isPending ? "Nahrávám…" : "Nahrát fotku (PNG/JPG/WEBP/HEIC, max 5 MB)"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/heic,.heic"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploadMutation.isPending}
            />
          </label>
        </div>
      )}

      {!canUpload && canEdit && photos.length >= MAX_PHOTOS && (
        <p className="text-xs text-gray-500 italic">
          Dosažen maximální počet fotek ({MAX_PHOTOS}). Smažte některou pro nahrání další.
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-gray-400 py-4">
          <Loader2 className="h-4 w-4 animate-spin" /> Načítám…
        </div>
      ) : photos.length === 0 ? (
        <p className="text-xs text-gray-400 italic py-2">Žádné fotky</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {photos.map((p) => (
            <div key={p.id} className="rounded-md border border-gray-200 overflow-hidden bg-white">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/v1/accident-photos/${p.id}/file`}
                alt={p.caption || "Foto úrazu"}
                className="w-full h-40 object-cover bg-gray-50"
                onError={(e) => { (e.target as HTMLImageElement).style.opacity = "0.3"; }}
              />
              <div className="p-2 space-y-1">
                {p.caption && <p className="text-xs text-gray-700 line-clamp-2">{p.caption}</p>}
                <div className="flex items-center justify-between">
                  <a
                    href={`/api/v1/accident-photos/${p.id}/file`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                  >
                    <Download className="h-3 w-3" /> Otevřít
                  </a>
                  {canEdit && (
                    <Tooltip label="Smazat fotku" side="left">
                      <button
                        onClick={() => {
                          if (confirm("Opravdu smazat tuto fotku?"))
                            deleteMutation.mutate(p.id);
                        }}
                        className="text-xs text-gray-400 hover:text-red-600"
                        aria-label="Smazat"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </Tooltip>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Podepsaný papírový dokument ──────────────────────────────────────────────

function SignedDocumentSection({
  accidentId,
  reportStatus,
}: {
  accidentId: string;
  reportStatus: "draft" | "final" | "archived";
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  // Stáhneme detail úrazu, abychom věděli, zda už dokument existuje
  const { data: report } = useQuery<AccidentReport>({
    queryKey: ["accident-report", accidentId],
    queryFn: () => api.get(`/accident-reports/${accidentId}`),
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;
      const headers: Record<string, string> = {};
      if (csrf) headers["X-CSRF-Token"] = csrf;

      const res = await fetch(`/api/v1/accident-reports/${accidentId}/signed-document`, {
        method: "POST",
        headers,
        body: formData,
        credentials: "same-origin",
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const err = await res.json();
          if (typeof err.detail === "string") detail = err.detail;
        } catch {}
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-report", accidentId] });
      qc.invalidateQueries({ queryKey: ["accident-reports"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba uploadu"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/accident-reports/${accidentId}/signed-document`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-report", accidentId] });
      qc.invalidateQueries({ queryKey: ["accident-reports"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const canEdit = reportStatus !== "archived";
  const hasDocument = !!report?.signed_document_path;

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    uploadMutation.mutate(file);
    e.target.value = "";
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <FileSignature className="h-4 w-4 text-blue-600" />
          Podepsaný papírový záznam
        </h3>
      </div>

      <p className="text-xs text-gray-500">
        Po vytištění a podepsání záznamu nahrajte sken nebo fotografii — slouží
        jako právní důkaz souhlasu zaměstnance, svědků a vedoucího pracoviště.
      </p>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {hasDocument ? (
        <div className="rounded-md border border-gray-200 bg-white p-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <FileSignature className="h-5 w-5 text-blue-600 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                Podepsaný záznam nahrán
              </p>
              <p className="text-xs text-gray-500 truncate">
                {report?.signed_document_path?.split("/").pop()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Tooltip label="Otevřít / stáhnout">
              <a
                href={`/api/v1/accident-reports/${accidentId}/signed-document/file`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50"
                aria-label="Otevřít dokument"
              >
                <Download className="h-4 w-4" />
              </a>
            </Tooltip>
            {canEdit && (
              <>
                <Tooltip label="Nahradit jiným souborem">
                  <label
                    className="inline-flex items-center gap-1 cursor-pointer rounded p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50"
                    aria-label="Nahradit"
                  >
                    <Upload className="h-4 w-4" />
                    <input
                      type="file"
                      accept="application/pdf,image/png,image/jpeg,image/webp,image/heic,.pdf,.heic"
                      className="hidden"
                      onChange={handleFileChange}
                      disabled={uploadMutation.isPending}
                    />
                  </label>
                </Tooltip>
                <Tooltip label="Smazat dokument">
                  <button
                    onClick={() => {
                      if (confirm("Opravdu smazat podepsaný dokument?"))
                        deleteMutation.mutate();
                    }}
                    className="rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50"
                    aria-label="Smazat"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </Tooltip>
              </>
            )}
          </div>
        </div>
      ) : canEdit ? (
        <label className="flex items-center justify-center gap-2 cursor-pointer rounded-md border border-dashed border-blue-300 bg-blue-50 hover:bg-blue-100 transition-colors px-3 py-3 text-sm font-medium text-blue-700">
          <Upload className="h-4 w-4" />
          {uploadMutation.isPending ? "Nahrávám…" : "Nahrát podepsaný dokument (PDF nebo sken, max 5 MB)"}
          <input
            type="file"
            accept="application/pdf,image/png,image/jpeg,image/webp,image/heic,.pdf,.heic"
            className="hidden"
            onChange={handleFileChange}
            disabled={uploadMutation.isPending}
          />
        </label>
      ) : (
        <p className="text-xs text-gray-400 italic">Žádný dokument nebyl nahrán</p>
      )}
    </div>
  );
}

// ── Hlavní panel ─────────────────────────────────────────────────────────────

export function AccidentDetailPanel({
  accidentId,
  reportStatus,
}: {
  accidentId: string;
  reportStatus: "draft" | "final" | "archived";
}) {
  return (
    <div className="space-y-6">
      {reportStatus === "draft" && (
        <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
          Záznam je rozpracovaný. Akční plán bude automaticky vytvořen po finalizaci nahlášení.
        </div>
      )}
      <ActionPlanSection accidentId={accidentId} reportStatus={reportStatus} />
      <div className="border-t border-gray-100" />
      <PhotosSection accidentId={accidentId} reportStatus={reportStatus} />
      <div className="border-t border-gray-100" />
      <SignedDocumentSection accidentId={accidentId} reportStatus={reportStatus} />
    </div>
  );
}
