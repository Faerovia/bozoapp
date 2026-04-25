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
  Plus, FileText, Sparkles, Loader2, Upload,
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
import { DocumentEditor } from "./document-editor";
import { FolderTree, type DocumentFolderItem } from "./folder-tree";
import { ImportDocumentDialog } from "./import-dialog";

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const TYPE_BADGES: Record<DocumentType, string> = {
  bozp_directive: "bg-purple-100 text-purple-700",
  training_outline: "bg-blue-100 text-blue-700",
  revision_schedule: "bg-emerald-100 text-emerald-700",
  risk_categorization: "bg-amber-100 text-amber-700",
  imported: "bg-gray-100 text-gray-700",
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

// ── Stránka ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  // null = "Vše" pro aktuální doménu, jinak ID složky. Před první volbou: undefined → vše.
  const [selectedFolderId, setSelectedFolderId] = useState<string | null | undefined>(undefined);

  const { data: docs = [], isLoading } = useQuery<GeneratedDocumentListItem[]>({
    queryKey: ["documents", selectedFolderId],
    queryFn: () => {
      if (selectedFolderId === undefined) return api.get("/documents");
      const qs = selectedFolderId === null ? "?root_only=true" : `?folder_id=${selectedFolderId}`;
      return api.get(`/documents${qs}`);
    },
  });

  // Folders pro import dialog (všechny domény)
  const { data: allFolders = [] } = useQuery<DocumentFolderItem[]>({
    queryKey: ["document-folders", "all"],
    queryFn: () => api.get("/document-folders"),
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
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="h-4 w-4 mr-1.5" />
              Importovat
            </Button>
            <Button size="sm" onClick={() => setGenerateOpen(true)}>
              <Plus className="h-4 w-4 mr-1.5" />
              Vygenerovat
            </Button>
          </div>
        }
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Folder tree — úplně vlevo */}
        <div className="w-72 border-r border-gray-200 bg-white">
          <FolderTree
            selectedFolderId={selectedFolderId === undefined ? null : selectedFolderId}
            onSelectFolder={(id) => {
              setSelectedFolderId(id);
              setSelectedId(null);
            }}
          />
        </div>

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

      <ImportDocumentDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        folders={allFolders}
        defaultFolderId={selectedFolderId === undefined ? null : selectedFolderId}
        onImported={(id) => {
          setImportOpen(false);
          setSelectedId(id);
        }}
      />
    </div>
  );
}
