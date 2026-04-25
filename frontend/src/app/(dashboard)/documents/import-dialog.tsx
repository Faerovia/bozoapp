"use client";

/**
 * Import existujícího dokumentu (PDF / DOCX / MD / TXT) jako 'imported'
 * GeneratedDocument do vybrané složky.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import type { DocumentFolderItem } from "./folder-tree";

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

export function ImportDocumentDialog({
  open,
  onClose,
  folders,
  defaultFolderId,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  folders: DocumentFolderItem[];
  defaultFolderId: string | null;
  onImported: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folderId, setFolderId] = useState<string>(defaultFolderId ?? "");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file || !title.trim()) {
        throw new ApiError(400, "Vyplňte název i soubor");
      }
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", title.trim());
      if (folderId) formData.append("folder_id", folderId);

      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;
      const headers: Record<string, string> = {};
      if (csrf) headers["X-CSRF-Token"] = csrf;

      const res = await fetch("/api/v1/document-folders/import", {
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
      return res.json() as Promise<{ id: string }>;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      setFile(null); setTitle(""); setError(null);
      onImported(data.id);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba uploadu"),
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    if (!title) {
      // Auto-fill title z názvu souboru (bez extension)
      const stem = f.name.replace(/\.[^.]+$/, "");
      setTitle(stem);
    }
  }

  // Folders pro select — seřazeno podle code
  const folderOptions = [...folders].sort((a, b) => a.code.localeCompare(b.code));

  return (
    <Dialog
      open={open}
      onClose={() => { setFile(null); setTitle(""); setError(null); onClose(); }}
      title="Import existujícího dokumentu"
      size="md"
    >
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Naimportujte existující dokument (PDF, DOCX, Markdown, TXT) do
          databáze. Text se z PDF/DOCX automaticky extrahuje a uloží jako
          editovatelný Markdown.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="imp-file">Soubor *</Label>
          <Input
            id="imp-file"
            type="file"
            accept=".pdf,.docx,.md,.txt,application/pdf"
            onChange={handleFileChange}
          />
          <p className="text-xs text-gray-400">
            Povoleno: PDF, DOCX, MD, TXT (max 10 MB). Skenované PDF bez OCR
            nepůjde — bude prázdný text.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="imp-title">Název dokumentu *</Label>
          <Input
            id="imp-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="např. Provozní řád skladu A"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="imp-folder">Složka</Label>
          <select
            id="imp-folder"
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">— Bez složky (kořen) —</option>
            {folderOptions.map(f => (
              <option key={f.id} value={f.id}>
                [{f.code}] {f.name} ({f.domain.toUpperCase()})
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Zrušit</Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!file || !title.trim()}
          >
            <Upload className="h-3.5 w-3.5 mr-1.5" /> Importovat
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
