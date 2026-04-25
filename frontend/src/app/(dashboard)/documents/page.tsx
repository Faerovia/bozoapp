"use client";

/**
 * Generátor BOZP/PO dokumentů.
 *
 * Layout 2-pane:
 *  - Levý panel: list všech vygenerovaných dokumentů + button „Vygenerovat"
 *  - Pravý panel: zvolený dokument — title editor + Markdown editor + akce
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, FileText, Trash2, Save, Sparkles, Database, Loader2, Download,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  DocumentType, GeneratedDocument, GeneratedDocumentListItem, JobPosition,
} from "@/types/api";
import { DOCUMENT_TYPE_LABELS, DOCUMENT_TYPE_DESC } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const TYPE_BADGES: Record<DocumentType, string> = {
  bozp_directive: "bg-purple-100 text-purple-700",
  training_outline: "bg-blue-100 text-blue-700",
  revision_schedule: "bg-emerald-100 text-emerald-700",
  risk_categorization: "bg-amber-100 text-amber-700",
};

function isAiType(t: DocumentType): boolean {
  return t === "bozp_directive" || t === "training_outline";
}

function errMsg(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Chyba serveru";
}

// ── Generate dialog ────────────────────────────────────────────────────────

function GenerateDialog({
  open,
  onClose,
  onGenerated,
}: {
  open: boolean;
  onClose: () => void;
  onGenerated: (id: string) => void;
}) {
  const [docType, setDocType] = useState<DocumentType>("revision_schedule");
  const [positionId, setPositionId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions", "active"],
    queryFn: () => api.get("/job-positions?jp_status=active"),
    enabled: open && docType === "training_outline",
  });

  const generate = useMutation({
    mutationFn: () => {
      const params: Record<string, unknown> = {};
      if (docType === "training_outline") params.position_id = positionId;
      return api.post<GeneratedDocument>("/documents/generate", {
        document_type: docType,
        params,
      });
    },
    onSuccess: (doc) => {
      setError(null);
      onGenerated(doc.id);
    },
    onError: (err) => setError(errMsg(err)),
  });

  // Reset error/position při změně typu
  useEffect(() => {
    setError(null);
    setPositionId("");
  }, [docType]);

  const canGenerate = docType !== "training_outline" || !!positionId;

  return (
    <Dialog open={open} onClose={onClose} title="Vygenerovat dokument" size="md">
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="dtype">Typ dokumentu</Label>
          <select
            id="dtype"
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocumentType)}
            className={SELECT_CLS}
          >
            {(Object.keys(DOCUMENT_TYPE_LABELS) as DocumentType[]).map((t) => (
              <option key={t} value={t}>
                {DOCUMENT_TYPE_LABELS[t]}{isAiType(t) ? "  •  AI" : "  •  z dat"}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            {DOCUMENT_TYPE_DESC[docType]}
          </p>
        </div>

        {docType === "training_outline" && (
          <div className="space-y-1.5">
            <Label htmlFor="pos">Pracovní pozice</Label>
            <select
              id="pos"
              value={positionId}
              onChange={(e) => setPositionId(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">— vyber pozici —</option>
              {positions.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.workplace_name ? ` · ${p.workplace_name}` : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {isAiType(docType) && (
          <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
            <Sparkles className="inline h-3.5 w-3.5 mr-1" />
            Generování AI dokumentu může trvat 30—60 sekund. Vyčkej.
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Zrušit</Button>
          <Button
            disabled={!canGenerate || generate.isPending}
            loading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
            {!generate.isPending && <Sparkles className="h-4 w-4 mr-1.5" />}
            Vygenerovat
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

// ── Editor pane ────────────────────────────────────────────────────────────

function DocumentEditor({
  docId,
}: {
  docId: string;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [contentMd, setContentMd] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: doc, isLoading } = useQuery<GeneratedDocument>({
    queryKey: ["document", docId],
    queryFn: () => api.get(`/documents/${docId}`),
  });

  // Sync local state s loaded doc
  useEffect(() => {
    if (doc) {
      setTitle(doc.title);
      setContentMd(doc.content_md);
      setDirty(false);
      setSaveError(null);
    }
  }, [doc]);

  const save = useMutation({
    mutationFn: () =>
      api.patch<GeneratedDocument>(`/documents/${docId}`, {
        title,
        content_md: contentMd,
      }),
    onSuccess: () => {
      setDirty(false);
      setSaveError(null);
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err) => setSaveError(errMsg(err)),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/documents/${docId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.removeQueries({ queryKey: ["document", docId] });
    },
  });

  if (isLoading || !doc) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
        <FileText className="h-5 w-5 text-gray-400 shrink-0" />
        <Input
          value={title}
          onChange={(e) => { setTitle(e.target.value); setDirty(true); }}
          className="flex-1 font-semibold border-transparent hover:border-gray-200 focus:border-blue-500"
          placeholder="Název dokumentu"
        />
        <span className={cn(
          "rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
          TYPE_BADGES[doc.document_type]
        )}>
          {DOCUMENT_TYPE_LABELS[doc.document_type].split("(")[0].trim()}
        </span>
      </div>

      {/* Toolbar */}
      <div className="border-b border-gray-100 bg-gray-50/50 px-4 py-2 flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {doc.ai_input_tokens != null && (
            <>
              <Sparkles className="inline h-3 w-3 mr-1 text-blue-500" />
              AI tokens: {doc.ai_input_tokens} input / {doc.ai_output_tokens} output
            </>
          )}
          {doc.ai_input_tokens == null && (
            <>
              <Database className="inline h-3 w-3 mr-1 text-emerald-500" />
              Generováno z dat (bez AI)
            </>
          )}
        </span>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              window.open(`/api/v1/documents/${docId}/pdf?download=true`, "_blank")
            }
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            Stáhnout PDF
          </Button>
          <Button
            size="sm"
            disabled={!dirty || save.isPending}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            <Save className="h-3.5 w-3.5 mr-1" />
            Uložit
          </Button>
          <button
            onClick={() => {
              if (confirm("Opravdu smazat tento dokument?")) remove.mutate();
            }}
            className="rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            title="Smazat"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {saveError && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 text-sm text-red-700">
          {saveError}
        </div>
      )}

      {/* Editor */}
      <textarea
        value={contentMd}
        onChange={(e) => { setContentMd(e.target.value); setDirty(true); }}
        className="flex-1 w-full px-6 py-4 text-sm font-mono leading-relaxed resize-none focus:outline-none bg-white"
        placeholder="Markdown obsah dokumentu…"
        spellCheck={false}
      />
    </div>
  );
}

// ── Stránka ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);

  const { data: docs = [], isLoading } = useQuery<GeneratedDocumentListItem[]>({
    queryKey: ["documents"],
    queryFn: () => api.get("/documents"),
  });

  // Auto-select první dokument
  useEffect(() => {
    if (!selectedId && docs.length > 0) {
      setSelectedId(docs[0].id);
    }
    // Pokud vybraný byl smazán, vyber první
    if (selectedId && !docs.find((d) => d.id === selectedId)) {
      setSelectedId(docs[0]?.id ?? null);
    }
  }, [docs, selectedId]);

  return (
    <div className="flex flex-col h-screen">
      <Header
        title="Dokumenty"
        actions={
          <Button size="sm" onClick={() => setGenerateOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            Vygenerovat
          </Button>
        }
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Levý panel — list */}
        <div className="w-72 border-r border-gray-200 bg-white flex flex-col overflow-hidden">
          {isLoading ? (
            <div className="p-3 space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-12 bg-gray-50 rounded animate-pulse" />
              ))}
            </div>
          ) : docs.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-gray-400">
              <FileText className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">Žádné dokumenty</p>
              <p className="text-xs mt-1">Klikni &bdquo;Vygenerovat&ldquo; pro první</p>
            </div>
          ) : (
            <ul className="flex-1 overflow-y-auto divide-y divide-gray-100">
              {docs.map((doc) => {
                const active = doc.id === selectedId;
                return (
                  <li key={doc.id}>
                    <button
                      onClick={() => setSelectedId(doc.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors",
                        active && "bg-blue-50 hover:bg-blue-50"
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <FileText className={cn(
                          "h-4 w-4 shrink-0 mt-0.5",
                          active ? "text-blue-600" : "text-gray-400"
                        )} />
                        <div className="min-w-0 flex-1">
                          <div className={cn(
                            "text-sm truncate",
                            active ? "font-semibold text-blue-700" : "font-medium text-gray-800"
                          )}>
                            {doc.title}
                          </div>
                          <div className="mt-0.5">
                            <span className={cn(
                              "rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase",
                              TYPE_BADGES[doc.document_type]
                            )}>
                              {DOCUMENT_TYPE_LABELS[doc.document_type].split("(")[0].trim()}
                            </span>
                          </div>
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Pravý panel — editor */}
        <div className="flex-1 overflow-hidden">
          {selectedId ? (
            <DocumentEditor docId={selectedId} />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">
              <div className="text-center">
                <FileText className="h-12 w-12 mx-auto opacity-30 mb-3" />
                <p>Vyber dokument vlevo nebo vygeneruj nový.</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <GenerateDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        onGenerated={(id) => {
          setGenerateOpen(false);
          setSelectedId(id);
        }}
      />
    </div>
  );
}
