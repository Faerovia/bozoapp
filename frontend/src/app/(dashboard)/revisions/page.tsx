"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Pencil, Trash2, Download, QrCode, ExternalLink } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Revision, Plant, DeviceType } from "@/types/api";
import { DEVICE_TYPE_LABELS } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const DUE_STATUS_LABELS: Record<string, string> = {
  ok:           "V pořádku",
  due_soon:     "Blíží se (≤30 dní)",
  upcoming:     "Blíží se",
  overdue:      "PO TERMÍNU",
  no_schedule:  "Bez termínu",
};

const DUE_STATUS_COLORS: Record<string, string> = {
  ok:           "bg-green-100 text-green-700",
  due_soon:     "bg-amber-100 text-amber-700",
  upcoming:     "bg-amber-100 text-amber-700",
  overdue:      "bg-red-100 text-red-700",
  no_schedule:  "bg-gray-100 text-gray-500",
};

const DEVICE_TYPE_OPTIONS: { value: DeviceType; label: string }[] =
  (Object.entries(DEVICE_TYPE_LABELS) as [DeviceType, string][])
    .map(([value, label]) => ({ value, label }));

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  title:             z.string().min(1, "Název je povinný"),
  plant_id:          z.string().min(1, "Provozovna je povinná"),
  device_type:       z.enum(
    ["elektro","hromosvody","plyn","kotle","tlakove_nadoby","vytahy","spalinove_cesty"],
    { errorMap: () => ({ message: "Vyber typ zařízení" }) }
  ),
  device_code:       z.string().optional().transform(v => v || null),
  location:          z.string().optional().transform(v => v || null),
  last_revised_at:   z.string().optional().transform(v => v || null),
  valid_months:      z.string().min(1, "Periodicita je povinná")
    .transform(v => parseInt(v, 10))
    .refine(v => v > 0 && v <= 600, "Neplatná hodnota"),
  technician_name:   z.string().optional().transform(v => v || null),
  technician_email:  z.string().optional().transform(v => v || null)
    .refine(v => v === null || /^[^@]+@[^@]+\.[^@]+$/.test(v), "Neplatný e-mail"),
  technician_phone:  z.string().optional().transform(v => v || null),
  notes:             z.string().optional().transform(v => v || null),
});

type FormData = z.infer<typeof schema>;

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Formulář ─────────────────────────────────────────────────────────────────

function RevisionForm({
  defaultValues,
  plants,
  onSubmit,
  isSubmitting,
  serverError,
}: {
  defaultValues?: Partial<FormData>;
  plants: Plant[];
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? {},
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5 col-span-2">
          <Label htmlFor="title">Název zařízení *</Label>
          <Input id="title" {...register("title")} placeholder="Elektrorozvaděč R1" />
          {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="plant_id">Provozovna *</Label>
          <select id="plant_id" {...register("plant_id")} className={SELECT_CLS}>
            <option value="">— vyber —</option>
            {plants.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {errors.plant_id && <p className="text-xs text-red-600">{errors.plant_id.message}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="device_type">Typ zařízení *</Label>
          <select id="device_type" {...register("device_type")} className={SELECT_CLS}>
            <option value="">— vyber —</option>
            {DEVICE_TYPE_OPTIONS.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          {errors.device_type && <p className="text-xs text-red-600">{errors.device_type.message}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="device_code">ID zařízení</Label>
          <Input id="device_code" {...register("device_code")} placeholder="RZV-001" />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="location">Upřesnění umístění</Label>
          <Input id="location" {...register("location")} placeholder="1. patro, místnost 105" />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="last_revised_at">Datum poslední revize</Label>
          <Input id="last_revised_at" type="date" {...register("last_revised_at")} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Periodicita (měsíce) *</Label>
          <Input id="valid_months" type="number" min="1" {...register("valid_months")} placeholder="60" />
          {errors.valid_months && <p className="text-xs text-red-600">{errors.valid_months.message}</p>}
          <p className="text-xs text-gray-400">Např. elektro = 60 měsíců (5 let)</p>
        </div>
      </div>

      <fieldset className="border border-gray-200 rounded-md p-3 space-y-3">
        <legend className="text-xs font-medium text-gray-500 px-1">
          Kontakt na revizního technika
        </legend>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="technician_name">Jméno / firma</Label>
            <Input id="technician_name" {...register("technician_name")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="technician_email">E-mail</Label>
            <Input id="technician_email" type="email" {...register("technician_email")} />
            {errors.technician_email && (
              <p className="text-xs text-red-600">{errors.technician_email.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="technician_phone">Telefon</Label>
            <Input id="technician_phone" {...register("technician_phone")} />
          </div>
        </div>
      </fieldset>

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
  const [plantFilter, setPlantFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [editRevision, setEditRevision] = useState<Revision | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants"),
  });

  const queryStr = [
    dueFilter   && `due_status=${dueFilter}`,
    plantFilter && `plant_id=${plantFilter}`,
    typeFilter  && `device_type=${typeFilter}`,
  ].filter(Boolean).join("&");

  const { data: revisions = [], isLoading } = useQuery<Revision[]>({
    queryKey: ["revisions", dueFilter, plantFilter, typeFilter],
    queryFn: () => api.get(`/revisions${queryStr ? `?${queryStr}` : ""}`),
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

  return (
    <div>
      <Header
        title="Revize"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat zařízení
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={cn(SELECT_CLS, "w-auto text-xs")}
            value={plantFilter}
            onChange={(e) => setPlantFilter(e.target.value)}
          >
            <option value="">Všechny provozovny</option>
            {plants.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <select
            className={cn(SELECT_CLS, "w-auto text-xs")}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">Všechny typy</option>
            {DEVICE_TYPE_OPTIONS.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>

          <div className="flex items-center gap-1">
            {(["", "overdue", "due_soon", "ok", "no_schedule"] as const).map(val => (
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
          </div>

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
                <p className="text-sm">Žádná zařízení</p>
                <p className="text-xs mt-1">Přidejte první zařízení tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zařízení</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Provozovna</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Posl. revize</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Další revize</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {revisions.map(rev => (
                      <tr key={rev.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4">
                          <Link
                            href={`/revisions/${rev.id}`}
                            className="font-medium text-gray-900 hover:text-blue-600"
                          >
                            {rev.title}
                          </Link>
                          {rev.device_code && (
                            <div className="text-xs text-gray-400">{rev.device_code}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{rev.plant_name || "—"}</td>
                        <td className="py-3 px-4 text-gray-600 text-xs">
                          {rev.device_type ? DEVICE_TYPE_LABELS[rev.device_type] : "—"}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(rev.last_revised_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(rev.next_revision_at)}</td>
                        <td className="py-3 px-4">
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            DUE_STATUS_COLORS[rev.due_status] || "bg-gray-100 text-gray-500"
                          )}>
                            {DUE_STATUS_LABELS[rev.due_status] || rev.due_status}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => window.open(`/api/v1/revisions/${rev.id}/qr.png`, "_blank")}
                              className="rounded p-1 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                              title="QR kód"
                            >
                              <QrCode className="h-3.5 w-3.5" />
                            </button>
                            <Link
                              href={`/revisions/${rev.id}`}
                              className="rounded p-1 text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                              title="Detail"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </Link>
                            <button
                              onClick={() => { setServerError(null); setEditRevision(rev); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Archivovat zařízení: ${rev.title}?`))
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

      {/* Dialog: Nové zařízení */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat zařízení"
        size="lg"
      >
        <RevisionForm
          plants={plants}
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
        />
      </Dialog>

      {/* Dialog: Upravit zařízení */}
      <Dialog
        open={!!editRevision}
        onClose={() => setEditRevision(null)}
        title={editRevision ? `Upravit: ${editRevision.title}` : ""}
        size="lg"
      >
        {editRevision && (
          <RevisionForm
            plants={plants}
            defaultValues={{
              title:            editRevision.title,
              plant_id:         editRevision.plant_id ?? "",
              device_type:      (editRevision.device_type ?? undefined) as DeviceType | undefined,
              device_code:      editRevision.device_code ?? "",
              location:         editRevision.location ?? "",
              last_revised_at:  editRevision.last_revised_at ?? "",
              valid_months:     editRevision.valid_months ?? undefined,
              technician_name:  editRevision.technician_name ?? "",
              technician_email: editRevision.technician_email ?? "",
              technician_phone: editRevision.technician_phone ?? "",
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
