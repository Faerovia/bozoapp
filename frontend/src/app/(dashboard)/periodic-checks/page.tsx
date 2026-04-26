"use client";

/**
 * Modul Pravidelné kontroly: sanační sady, záchytné vany, lékárničky.
 * Layout je zjednodušená kopie /revisions:
 *  - filter podle check_kind a plant
 *  - tabulka s tlačítky: vyplnit kontrolu / upravit / archivovat
 *  - dialog pro novou kontrolu
 *  - dialog pro záznam o provedené kontrole
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Plus, Pencil, Trash2, ClipboardCheck, Info, ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  PeriodicCheck, PeriodicCheckRecord, CheckKind, Plant,
} from "@/types/api";
import { CHECK_KIND_LABELS, CHECK_KIND_PERIODICITY_INFO } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ── Konstanty ───────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const KIND_OPTIONS: { value: CheckKind; label: string }[] = [
  { value: "sanitation_kit", label: "Sanační sada" },
  { value: "spill_tray",     label: "Záchytná vana" },
  { value: "first_aid_kit",  label: "Lékárnička" },
];

const DUE_STATUS_LABELS: Record<string, string> = {
  ok: "V pořádku",
  due_soon: "Blíží se (≤30 dní)",
  upcoming: "Blíží se",
  overdue: "PO TERMÍNU",
  no_schedule: "Bez termínu",
};
const DUE_STATUS_COLORS: Record<string, string> = {
  ok: "bg-green-100 text-green-700",
  due_soon: "bg-amber-100 text-amber-700",
  upcoming: "bg-amber-100 text-amber-700",
  overdue: "bg-red-100 text-red-700",
  no_schedule: "bg-gray-100 text-gray-500",
};

// ── Schémata ────────────────────────────────────────────────────────────────

const checkSchema = z.object({
  check_kind: z.enum(["sanitation_kit", "spill_tray", "first_aid_kit"] as const, {
    errorMap: () => ({ message: "Vyber typ kontroly" }),
  }),
  title: z.string().min(1, "Název je povinný"),
  location: z.string().optional().transform((v) => v || null),
  plant_id: z.string().optional().transform((v) => v || null),
  last_checked_at: z.string().optional().transform((v) => v || null),
  valid_months: z.string().min(1, "Periodicita je povinná")
    .transform((v) => parseInt(v, 10))
    .refine((v) => v > 0 && v <= 600, "Neplatná hodnota"),
  notes: z.string().optional().transform((v) => v || null),
});

type CheckFormData = z.infer<typeof checkSchema>;

const recordSchema = z.object({
  performed_at: z.string().min(1, "Datum je povinné"),
  performed_by_name: z.string().optional().transform((v) => v || null),
  result: z.enum(["ok", "fixed", "issue"] as const).default("ok"),
  notes: z.string().optional().transform((v) => v || null),
});

type RecordFormData = z.infer<typeof recordSchema>;

// ── Form: nový/edit kontrolovaná položka ────────────────────────────────────

function CheckForm({
  defaultValues, plants, onSubmit, isSubmitting, serverError,
}: {
  defaultValues?: Partial<CheckFormData>;
  plants: Plant[];
  onSubmit: (d: CheckFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const { register, handleSubmit, watch, formState: { errors } } = useForm<CheckFormData>({
    resolver: zodResolver(checkSchema),
    defaultValues: defaultValues ?? {},
  });
  const selectedKind = watch("check_kind") as CheckKind | undefined;
  const periodInfo = selectedKind
    ? CHECK_KIND_PERIODICITY_INFO[selectedKind]
    : "Vyber typ kontroly výše — zobrazí se legislativní lhůty.";

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="check_kind">Typ kontroly *</Label>
          <select id="check_kind" {...register("check_kind")} className={SELECT_CLS}>
            <option value="">— vyber —</option>
            {KIND_OPTIONS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
          {errors.check_kind && <p className="text-xs text-red-600">{errors.check_kind.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="plant_id">Provozovna</Label>
          <select id="plant_id" {...register("plant_id")} className={SELECT_CLS}>
            <option value="">— bez plantu —</option>
            {plants.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="title">Název kontroly *</Label>
        <Input id="title" {...register("title")}
          placeholder="Lékárnička výroba A / Sanační sada sklad chemikálií" />
        {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="location">Upřesnění umístění</Label>
        <Input id="location" {...register("location")} placeholder="1. patro, hala C" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="last_checked_at">Datum poslední kontroly</Label>
          <Input id="last_checked_at" type="date" {...register("last_checked_at")} />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor="valid_months">Periodicita (měsíce) *</Label>
            <Tooltip label={periodInfo}>
              <Info className="h-3.5 w-3.5 text-blue-500 cursor-help" />
            </Tooltip>
          </div>
          <Input id="valid_months" type="number" min="1" {...register("valid_months")} placeholder="12" />
          {errors.valid_months && <p className="text-xs text-red-600">{errors.valid_months.message}</p>}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky</Label>
        <textarea id="notes" {...register("notes")} rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
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

// ── Form: záznam provedené kontroly ─────────────────────────────────────────

function RecordForm({
  onSubmit, isSubmitting, serverError,
}: {
  onSubmit: (d: RecordFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const { register, handleSubmit, formState: { errors } } = useForm<RecordFormData>({
    resolver: zodResolver(recordSchema),
    defaultValues: { performed_at: today, result: "ok" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="performed_at">Datum provedení *</Label>
          <Input id="performed_at" type="date" {...register("performed_at")} />
          {errors.performed_at && <p className="text-xs text-red-600">{errors.performed_at.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="result">Výsledek *</Label>
          <select id="result" {...register("result")} className={SELECT_CLS}>
            <option value="ok">V pořádku</option>
            <option value="fixed">Doplněno / opraveno</option>
            <option value="issue">Zjištěn problém</option>
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="performed_by_name">Provedl (jméno)</Label>
        <Input id="performed_by_name" {...register("performed_by_name")} placeholder="Jan Novák" />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky / popis úkonu</Label>
        <textarea id="notes" {...register("notes")} rows={3}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          placeholder="Doplněna lékárnička: 4× obvazy, 2× náplast, kontrola expirace léčiv (nejbližší 03/2027)." />
      </div>

      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {serverError}
        </div>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" loading={isSubmitting}>Uložit záznam</Button>
      </div>
    </form>
  );
}

// ── Stránka ─────────────────────────────────────────────────────────────────

export default function PeriodicChecksPage() {
  const qc = useQueryClient();
  const [kindFilter, setKindFilter] = useState<string>("");
  const [plantFilter, setPlantFilter] = useState<string>("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editCheck, setEditCheck] = useState<PeriodicCheck | null>(null);
  const [recordCheck, setRecordCheck] = useState<PeriodicCheck | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: checks = [], isLoading } = useQuery<PeriodicCheck[]>({
    queryKey: ["periodic-checks", kindFilter, plantFilter],
    queryFn: () => {
      const p = new URLSearchParams();
      if (kindFilter) p.set("check_kind", kindFilter);
      if (plantFilter) p.set("plant_id", plantFilter);
      p.set("check_status", "active");
      return api.get(`/periodic-checks?${p.toString()}`);
    },
  });

  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants?plant_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMut = useMutation({
    mutationFn: (d: CheckFormData) => api.post<PeriodicCheck>("/periodic-checks", d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["periodic-checks"] });
      setCreateOpen(false);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMut = useMutation({
    mutationFn: (d: { id: string; data: Partial<CheckFormData> }) =>
      api.patch(`/periodic-checks/${d.id}`, d.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["periodic-checks"] });
      setEditCheck(null);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const archiveMut = useMutation({
    mutationFn: (id: string) => api.delete(`/periodic-checks/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["periodic-checks"] }),
  });

  const recordMut = useMutation({
    mutationFn: (d: { id: string; data: RecordFormData }) =>
      api.post<PeriodicCheckRecord>(`/periodic-checks/${d.id}/records`, d.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["periodic-checks"] });
      setRecordCheck(null);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function fmtDate(s: string | null) {
    if (!s) return "—";
    return new Date(s).toLocaleDateString("cs-CZ");
  }

  return (
    <div>
      <Header
        title="Pravidelné kontroly"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat kontrolu
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end bg-gray-50 border border-gray-200 rounded-md p-3">
          <div>
            <Label htmlFor="f-kind" className="text-xs text-gray-600">Typ</Label>
            <select
              id="f-kind"
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              {KIND_OPTIONS.map((k) => (
                <option key={k.value} value={k.value}>{k.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="f-plant" className="text-xs text-gray-600">Provozovna</Label>
            <select
              id="f-plant"
              value={plantFilter}
              onChange={(e) => setPlantFilter(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              {plants.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="text-xs text-gray-500 pb-2 text-right">
            Aktivních záznamů: <strong>{checks.length}</strong>
          </div>
        </div>

        {/* Tabulka */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 text-sm text-gray-400">Načítám…</div>
            ) : checks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <ShieldCheck className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné kontroly</p>
                <p className="text-xs mt-1">Přidejte první kontrolu (sanační sada, vana, lékárnička)</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Typ</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Název</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Provozovna</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Poslední</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Další</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {checks.map((c) => (
                      <tr key={c.id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 text-xs text-gray-600 uppercase">
                          {CHECK_KIND_LABELS[c.check_kind]}
                        </td>
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {c.title}
                          {c.location && <span className="block text-xs text-gray-500">{c.location}</span>}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{c.plant_name || "—"}</td>
                        <td className="py-3 px-4 text-gray-600">{fmtDate(c.last_checked_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{fmtDate(c.next_check_at)}</td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", DUE_STATUS_COLORS[c.due_status])}>
                            {DUE_STATUS_LABELS[c.due_status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setRecordCheck(c); }}
                              className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50"
                              title="Zaznamenat provedenou kontrolu"
                            >
                              <ClipboardCheck className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => { setServerError(null); setEditCheck(c); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Archivovat kontrolu „${c.title}“?`))
                                  archiveMut.mutate(c.id);
                              }}
                              className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
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

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="Nová kontrola" size="lg">
        <CheckForm
          plants={plants}
          onSubmit={(d) => createMut.mutate(d)}
          isSubmitting={createMut.isPending}
          serverError={serverError}
        />
      </Dialog>

      <Dialog
        open={!!editCheck}
        onClose={() => setEditCheck(null)}
        title={editCheck ? `Upravit: ${editCheck.title}` : ""}
        size="lg"
      >
        {editCheck && (
          <CheckForm
            plants={plants}
            defaultValues={{
              check_kind: editCheck.check_kind,
              title: editCheck.title,
              location: editCheck.location ?? "",
              plant_id: editCheck.plant_id ?? "",
              last_checked_at: editCheck.last_checked_at ?? "",
              valid_months: editCheck.valid_months ?? undefined,
              notes: editCheck.notes ?? "",
            }}
            onSubmit={(d) => updateMut.mutate({ id: editCheck.id, data: d })}
            isSubmitting={updateMut.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>

      <Dialog
        open={!!recordCheck}
        onClose={() => setRecordCheck(null)}
        title={recordCheck ? `Záznam kontroly — ${recordCheck.title}` : ""}
        size="md"
      >
        {recordCheck && (
          <RecordForm
            onSubmit={(d) => recordMut.mutate({ id: recordCheck.id, data: d })}
            isSubmitting={recordMut.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>
    </div>
  );
}
