"use client";

/**
 * Subdomain editor — inline editor pro tenants.slug v platform admin.
 *
 * Slug určuje URL `{slug}.digitalozo.cz` (prod) nebo `{slug}.localhost:3000`
 * (dev). Validace na klientovi (regex + reserved) i serveru.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Check, X, ExternalLink, Globe } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { subdomainUrl } from "@/hooks/use-tenant-context";
import { cn } from "@/lib/utils";

const RESERVED = new Set([
  "admin", "www", "api", "app", "static", "cdn", "mail", "ftp",
]);
const SLUG_REGEX = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

function validateSlug(value: string): string | null {
  if (!value) return "Slug je povinný";
  if (value.length < 2) return "Minimum 2 znaky";
  if (value.length > 63) return "Maximum 63 znaků";
  if (!SLUG_REGEX.test(value)) {
    return "Jen malá písmena, číslice a pomlčky. Nesmí začínat/končit pomlčkou.";
  }
  if (RESERVED.has(value)) return `'${value}' je rezervovaný (admin, www, api…)`;
  return null;
}

interface SubdomainEditorProps {
  tenantId: string;
  currentSlug: string;
  onSaved?: (newSlug: string) => void;
}

export function SubdomainEditor({ tenantId, currentSlug, onSaved }: SubdomainEditorProps) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(currentSlug);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (slug: string) =>
      api.patch(`/admin/tenants/${tenantId}`, { slug }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-tenant-overview"] });
      qc.invalidateQueries({ queryKey: ["admin-tenants"] });
      setEditing(false);
      setError(null);
      onSaved?.(draft);
    },
    onError: (err) => {
      if (err instanceof ApiError) setError(err.detail);
      else setError("Chyba při ukládání");
    },
  });

  const handleSave = () => {
    const v = draft.trim().toLowerCase();
    const validation = validateSlug(v);
    if (validation) {
      setError(validation);
      return;
    }
    if (v === currentSlug) {
      setEditing(false);
      return;
    }
    mutation.mutate(v);
  };

  const url = subdomainUrl(currentSlug);

  if (!editing) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <Globe className="h-3.5 w-3.5 text-gray-400 shrink-0" />
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-blue-600 hover:underline truncate"
          title={`Otevřít ${url}`}
        >
          {currentSlug}
          <ExternalLink className="inline h-3 w-3 ml-1 align-text-top text-gray-400" />
        </a>
        <button
          type="button"
          onClick={() => {
            setDraft(currentSlug);
            setEditing(true);
            setError(null);
          }}
          className="ml-1 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
          title="Upravit slug"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  const previewUrl = subdomainUrl(draft.trim().toLowerCase() || "<slug>");

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-2">
        <div className="flex-1 space-y-1">
          <Label htmlFor={`slug-${tenantId}`} className="text-xs">
            Subdomain slug
          </Label>
          <Input
            id={`slug-${tenantId}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={mutation.isPending}
            placeholder="napr-firma"
            className={cn("text-sm font-mono", error && "border-red-500")}
          />
        </div>
        <Button
          type="button"
          size="sm"
          onClick={handleSave}
          loading={mutation.isPending}
          className="shrink-0"
        >
          <Check className="h-3.5 w-3.5" />
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            setEditing(false);
            setError(null);
          }}
          disabled={mutation.isPending}
          className="shrink-0"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}
      <p className="text-xs text-gray-500">
        URL: <span className="font-mono text-gray-700">{previewUrl}</span>
      </p>
      <p className="text-xs text-amber-600">
        ⚠ Změna sluga okamžitě přesměruje stávající uživatele — staré bookmarky
        a odkazy na původní URL přestanou fungovat.
      </p>
    </div>
  );
}
