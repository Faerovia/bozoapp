"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Pencil, Trash2, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Revision } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const REVISION_TYPES: { value: string; label: string }[] = [
  { value: "electrical",       label: "Elektrorevize" },
  { value: "pressure",         label: "Tlaková zařízení" },
  { value: "fire_extinguisher",label: "Hasicí přístroje" },
  { value: "hydrant",          label: "Hydranty" },
  { value: "lightning_rod",    label: "Hromosvody" },
  { value: "gas",              label: "Plynová zařízení" },
  { value: "lifting",          label: "Zdvihací zařízení" },
  { value: "ventilation",      label: "Vzduchotechnika" },
  { value: "other",            label: "Jiné" },
];

const DUE_STATUS_LABELS: Record<string, string> = {
  upcoming:   "Blíží se",
  overdue:    "Po termínu",
  no_schedule: "Neplánováno",
};

const DUE_STATUS_COLORS: Record<string, string> = {
  upcoming:    "bg-amber-100 text-amber-700",
  overdue:     "bg-red-100 text-red-700",
  no_schedule: "bg-gray-100 text-gray-500",
};

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  title:               z.string().min(1, "Název je povinný"),
  revision_type:       z.string().min(1, "Typ revize je povinný"),
  location:            z.string().optional().transform(v => v || null),
  last_revised_at:     z.string().optional().transform(v => v || null),
  valid_months:        z.string().optional().transform(v => v ? parseInt(v, 10) : null),
  next_revision_at:    z.string().optional().transform(v => v || null),
  notes:               z.string().optional().transform(v => v || null),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function RevisionForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { revision_type: "electrical" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="title">Název *</Label>
        <Input id="title" {...register("title")} />
        {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="revision_type">Typ revize *</Label>
        <select id="revision_type" {...register("revision_type")} className={SELECT_CLS}>
          {REVISION_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        {errors.revision_type && <p className="text-xs text-red-600">{errors.revision_type.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="location">Pracoviště</Label>
        <Input id="location" {...register("location")} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="last_revised_at">Poslední revize</Label>
          <Input id="last_revised_at" type="date" {...register("last_revised_at")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Perioda (měsíce)</Label>
          <Input
            id="valid_months"
            type="number"
            min="1"
            {...register("valid_months")}
            placeholder="60"
          />
          <p className="text-xs text-gray-400">Např. Elektro = 5 let = 60 m</p>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="next_revision_at">Příští revize (přepíše výpočet)</Label>
        <Input id="next_revision_at" type="date" {...register("next_revision_at")} />
        <p className="text-xs text-gray-400">Přepíše výpočet z posledního + platnost</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky</Label>
        <textarea
          id="notes"
          {...register("notes")}
          rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {serverError}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function RevisionsPage() {
  const qc = useQueryClient();
  const [dueFilter, setDueFilter] = useState<string>("");
  const [editRevision, setEditRevision] = useState<Revision | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: revisions = [], isLoading } = useQuery<Revision[]>({
    queryKey: ["revisions", dueFilter],
    queryFn: () => api.get(`/revisions${dueFilter ? `?due_status=${dueFilter}` : ""}`),
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/revisions", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["revisions"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/revisions/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["revisions"] }); setEditRevision(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/revisions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["revisions"] }),
  });

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  function getRevisionTypeLabel(type: string) {
    return REVISION_TYPES.find(t => t.value === type)?.label || type;
  }

  return (
    <div>
      <Header
        title="Revize"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat revizi
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2">
          {(["", "upcoming", "overdue", "no_schedule"] as const).map(val => (
            <button
              key={val}
              onClick={() => setDueFilter(val)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                dueFilter === val
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              )}
            >
              {val === "" ? "Všechny" : DUE_STATUS_LABELS[val]}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{revisions.length} záznamů</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open("/api/v1/revisions/export/pdf", "_blank")}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            PDF
          </Button>
        </div>

        {/* Tabulka */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-0 divide-y divide-gray-50">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-12 animate-pulse bg-gray-50 mx-4 my-2 rounded" />
                ))}
              </div>
            ) : revisions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Plus className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné revize</p>
                <p className="text-xs mt-1">Přidejte první revizi tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Název</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Pracoviště</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Poslední revize</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Příští revize</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {revisions.map(rev => (
                      <tr key={rev.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">{rev.title}</td>
                        <td className="py-3 px-4 text-gray-600 text-xs">{getRevisionTypeLabel(rev.revision_type)}</td>
                        <td className="py-3 px-4 text-gray-600">{rev.location || "—"}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(rev.last_revised_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(rev.next_revision_at)}</td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", DUE_STATUS_COLORS[rev.due_status])}>
                            {DUE_STATUS_LABELS[rev.due_status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditRevision(rev); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Archivovat revizi: ${rev.title}?`))
                                  archiveMutation.mutate(rev.id);
                              }}
                              className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                              title="Archivovat"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dialog: Nová revize */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat revizi"
        size="md"
      >
        <RevisionForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
        />
      </Dialog>

      {/* Dialog: Upravit revizi */}
      <Dialog
        open={!!editRevision}
        onClose={() => setEditRevision(null)}
        title={editRevision ? `Upravit: ${editRevision.title}` : ""}
        size="md"
      >
        {editRevision && (
          <RevisionForm
            defaultValues={{
              title:            editRevision.title,
              revision_type:    editRevision.revision_type,
              location:         editRevision.location ?? "",
              last_revised_at:  editRevision.last_revised_at ?? "",
              valid_months:     editRevision.valid_months ?? undefined,
              next_revision_at: editRevision.next_revision_at ?? "",
              notes:            editRevision.notes ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editRevision.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>
    </div>
  );
}
