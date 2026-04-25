"use client";

/**
 * Adresářový strom pro modul Dokumentace.
 *
 * Hierarchická navigace BOZP / PO. Code je full path "000.001.005",
 * číslování automatické backendem. Užívatel volí pouze název.
 *
 * Filtruje seznam dokumentů — kliknutí na složku → onSelect(folderId).
 * Tlačítko "Kořen" (folderId = null) zobrazí dokumenty bez přiřazené složky.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, FolderTree as FolderTreeIcon, Folder, FolderPlus, Trash2, Home,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type DocumentDomain = "bozp" | "po";

export interface DocumentFolderItem {
  id: string;
  parent_id: string | null;
  code: string;
  name: string;
  domain: string;
  sort_order: number;
}

const DOMAIN_LABEL: Record<DocumentDomain, string> = {
  bozp: "BOZP",
  po:   "Požární ochrana",
};

// ── Strom: helper pro vnoření dle parent_id ──────────────────────────────────

function buildTree(folders: DocumentFolderItem[]): {
  roots: DocumentFolderItem[];
  childrenOf: Record<string, DocumentFolderItem[]>;
} {
  const childrenOf: Record<string, DocumentFolderItem[]> = {};
  const roots: DocumentFolderItem[] = [];
  for (const f of folders) {
    if (f.parent_id) {
      (childrenOf[f.parent_id] ??= []).push(f);
    } else {
      roots.push(f);
    }
  }
  // Sort by code (lexicographic protože "000.001" < "000.002")
  roots.sort((a, b) => a.code.localeCompare(b.code));
  for (const k of Object.keys(childrenOf)) {
    childrenOf[k].sort((a, b) => a.code.localeCompare(b.code));
  }
  return { roots, childrenOf };
}

// ── Folder node (rekurzivní) ──────────────────────────────────────────────────

function FolderNode({
  folder, childrenOf, expanded, onToggle, selectedId, onSelect, onAdd, onDelete,
}: {
  folder: DocumentFolderItem;
  childrenOf: Record<string, DocumentFolderItem[]>;
  expanded: Record<string, boolean>;
  onToggle: (id: string) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onAdd: (parentId: string | null) => void;
  onDelete: (folder: DocumentFolderItem) => void;
}) {
  const kids = childrenOf[folder.id] ?? [];
  const hasKids = kids.length > 0;
  const isOpen = expanded[folder.id] ?? true;
  const active = selectedId === folder.id;

  return (
    <li>
      <div
        className={cn(
          "group flex items-center gap-1 pr-1 hover:bg-gray-50 rounded",
          active && "bg-blue-50",
        )}
      >
        <button
          onClick={() => hasKids && onToggle(folder.id)}
          className="p-1 text-gray-400 hover:text-gray-700"
          aria-label={hasKids ? "Rozbalit / sbalit" : "Žádné podsložky"}
        >
          {hasKids ? (
            isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <span className="inline-block w-3.5" />
          )}
        </button>
        <button
          onClick={() => onSelect(folder.id)}
          className="flex-1 min-w-0 flex items-center gap-1.5 py-1 text-left"
        >
          <Folder className={cn("h-3.5 w-3.5 shrink-0", active ? "text-blue-600" : "text-amber-500")} />
          <span className={cn(
            "text-xs font-mono shrink-0 text-gray-400",
            active && "text-blue-600",
          )}>
            {folder.code}
          </span>
          <span className={cn(
            "text-xs truncate",
            active ? "font-semibold text-blue-700" : "text-gray-700",
          )}>
            {folder.name}
          </span>
        </button>
        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
          <Tooltip label="Přidat podsložku" side="left">
            <button
              onClick={() => onAdd(folder.id)}
              className="p-1 text-gray-400 hover:text-blue-600"
              aria-label="Přidat podsložku"
            >
              <FolderPlus className="h-3 w-3" />
            </button>
          </Tooltip>
          <Tooltip label="Smazat (jen pokud je prázdná)" side="left">
            <button
              onClick={() => onDelete(folder)}
              className="p-1 text-gray-400 hover:text-red-600"
              aria-label="Smazat"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </Tooltip>
        </div>
      </div>
      {hasKids && isOpen && (
        <ul className="pl-4 border-l border-gray-100 ml-2">
          {kids.map(k => (
            <FolderNode
              key={k.id}
              folder={k}
              childrenOf={childrenOf}
              expanded={expanded}
              onToggle={onToggle}
              selectedId={selectedId}
              onSelect={onSelect}
              onAdd={onAdd}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ── Vytvořit složku dialog ────────────────────────────────────────────────────

function CreateFolderDialog({
  open, onClose, parentId, defaultDomain,
}: {
  open: boolean;
  onClose: () => void;
  parentId: string | null;
  defaultDomain: DocumentDomain;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState<DocumentDomain>(defaultDomain);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.post<DocumentFolderItem>("/document-folders", {
      name: name.trim(), domain, parent_id: parentId,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document-folders"] });
      setName(""); setError(null);
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  return (
    <Dialog
      open={open}
      onClose={() => { setName(""); setError(null); onClose(); }}
      title={parentId ? "Nová podsložka" : "Nová root složka"}
      size="md"
    >
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="folder-name">Název *</Label>
          <Input
            id="folder-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="např. Bezpečnost a ochrana zdraví při práci"
            autoFocus
          />
          <p className="text-xs text-gray-400">
            Číslování (000, 000.001, …) bude přiřazeno automaticky podle pořadí
            vytvoření v této úrovni.
          </p>
        </div>
        {parentId === null && (
          <div className="space-y-1.5">
            <Label htmlFor="folder-domain">Doména *</Label>
            <select
              id="folder-domain"
              value={domain}
              onChange={(e) => setDomain(e.target.value as DocumentDomain)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="bozp">BOZP</option>
              <option value="po">Požární ochrana</option>
            </select>
          </div>
        )}
        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Zrušit</Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!name.trim()}
          >
            Vytvořit
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

// ── Hlavní komponenta ────────────────────────────────────────────────────────

export function FolderTree({
  selectedFolderId,
  onSelectFolder,
}: {
  selectedFolderId: string | null;
  onSelectFolder: (folderId: string | null) => void;
}) {
  const qc = useQueryClient();
  const [domain, setDomain] = useState<DocumentDomain>("bozp");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createParentId, setCreateParentId] = useState<string | null>(null);

  const { data: folders = [], isLoading } = useQuery<DocumentFolderItem[]>({
    queryKey: ["document-folders", domain],
    queryFn: () => api.get(`/document-folders?domain=${domain}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/document-folders/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["document-folders"] }),
    onError: (err) => alert(
      err instanceof ApiError ? err.detail : "Nelze smazat",
    ),
  });

  const { roots, childrenOf } = buildTree(folders);

  function toggle(id: string) {
    setExpanded(prev => ({ ...prev, [id]: !(prev[id] ?? true) }));
  }

  function handleAdd(parentId: string | null) {
    setCreateParentId(parentId);
    setCreateOpen(true);
  }

  function handleDelete(f: DocumentFolderItem) {
    if (!confirm(`Smazat složku "${f.code} ${f.name}"?`)) return;
    deleteMutation.mutate(f.id);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Domain switcher */}
      <div className="p-2 border-b border-gray-100 flex gap-1">
        {(["bozp", "po"] as const).map(d => (
          <button
            key={d}
            onClick={() => setDomain(d)}
            className={cn(
              "flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
              domain === d
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200",
            )}
          >
            {DOMAIN_LABEL[d]}
          </button>
        ))}
      </div>

      {/* Header s tlačítkem */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-600 uppercase tracking-wide">
          <FolderTreeIcon className="h-3.5 w-3.5" />
          Adresář
        </span>
        <Tooltip label="Nová root složka">
          <button
            onClick={() => handleAdd(null)}
            className="p-1 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50"
            aria-label="Nová root složka"
          >
            <FolderPlus className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <button
          onClick={() => onSelectFolder(null)}
          className={cn(
            "w-full flex items-center gap-1.5 rounded px-2 py-1 text-xs",
            selectedFolderId === null
              ? "bg-blue-50 text-blue-700 font-semibold"
              : "text-gray-500 hover:bg-gray-50",
          )}
        >
          <Home className="h-3.5 w-3.5" />
          Vše ({DOMAIN_LABEL[domain]})
        </button>
        {isLoading ? (
          <div className="text-xs text-gray-400 italic px-2 py-1">Načítám…</div>
        ) : roots.length === 0 ? (
          <div className="text-xs text-gray-400 italic px-2 py-2">
            Žádné složky. Klikněte na ikonu &bdquo;+&ldquo; nahoře pro vytvoření.
          </div>
        ) : (
          <ul>
            {roots.map(f => (
              <FolderNode
                key={f.id}
                folder={f}
                childrenOf={childrenOf}
                expanded={expanded}
                onToggle={toggle}
                selectedId={selectedFolderId}
                onSelect={onSelectFolder}
                onAdd={handleAdd}
                onDelete={handleDelete}
              />
            ))}
          </ul>
        )}
      </div>

      <CreateFolderDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        parentId={createParentId}
        defaultDomain={domain}
      />
    </div>
  );
}
