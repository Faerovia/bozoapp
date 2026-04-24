"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { GraduationCap, Plus, Pencil, Archive, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Training, Employee } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const TRAINING_TYPES = [
  { value: "bozp_initial",   label: "BOZP – vstupní školení" },
  { value: "bozp_periodic",  label: "BOZP – periodické školení" },
  { value: "fire_initial",   label: "PO – vstupní školení" },
  { value: "fire_periodic",  label: "PO – periodické školení" },
  { value: "first_aid",      label: "První pomoc" },
  { value: "driver",         label: "Řidičské oprávnění / Řidiči referenti" },
  { value: "machinery",      label: "Obsluha strojů a zařízení" },
  { value: "chemical",       label: "Nakládání s chemickými látkami" },
  { value: "other",          label: "Jiné" },
];

const VALIDITY_COLORS: Record<string, string> = {
  no_expiry:     "bg-gray-100 text-gray-500",
  valid:         "bg-green-100 text-green-700",
  expiring_soon: "bg-amber-100 text-amber-700",
  expired:       "bg-red-100 text-red-700",
};

const VALIDITY_LABELS: Record<string, string> = {
  no_expiry:     "Bez expirace",
  valid:         "Platné",
  expiring_soon: "Expiruje brzy",
  expired:       "Expirováno",
};

// ── Schéma ───────────────────────────────────────────────────────────────────

const schema = z.object({
  employee_id:   z.string().uuid("Vyberte zaměstnance"),
  title:         z.string().min(1, "Název je povinný"),
  training_type: z.string().min(1),
  trained_at:    z.string().min(1, "Datum školení je povinné"),
  valid_months:  z.coerce.number().int().positive().optional().or(z.literal("")),
  trainer_name:  z.string().optional(),
  notes:         z.string().optional(),
});

type FormData = z.infer<typeof schema>;

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Formulář ─────────────────────────────────────────────────────────────────

function TrainingForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  employees,
  isEdit,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  employees: Employee[];
  isEdit?: boolean;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { training_type: "bozp_initial" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
            <option value="">— Vyberte zaměstnance —</option>
            {employees.map(e => (
              <option key={e.id} value={e.id}>
                {e.last_name} {e.first_name}
              </option>
            ))}
          </select>
          {errors.employee_id && <p className="text-xs text-red-600">{errors.employee_id.message}</p>}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="title">Název školení *</Label>
        <Input id="title" {...register("title")} placeholder="např. BOZP vstupní školení 2025" />
        {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="training_type">Typ školení *</Label>
        <select id="training_type" {...register("training_type")} className={SELECT_CLS}>
          {TRAINING_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="trained_at">Datum školení *</Label>
          <Input id="trained_at" type="date" {...register("trained_at")} />
          {errors.trained_at && <p className="text-xs text-red-600">{errors.trained_at.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Platnost (měsíce)</Label>
          <Input
            id="valid_months"
            type="number"
            min={1}
            max={120}
            placeholder="prázdné = bez expirace"
            {...register("valid_months")}
          />
          <p className="text-xs text-gray-400">BOZP = 24 m, PO = 12–24 m</p>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="trainer_name">Školitel</Label>
        <Input id="trainer_name" {...register("trainer_name")} placeholder="Jméno školitele" />
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

      <div className="flex justify-end pt-2">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function TrainingsPage() {
  const qc = useQueryClient();
  const [validityFilter, setValidityFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editTraining, setEditTraining] = useState<Training | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const params = validityFilter ? `?validity_status=${validityFilter}` : "";

  const { data: trainings = [], isLoading } = useQuery<Training[]>({
    queryKey: ["trainings", validityFilter],
    queryFn: () => api.get(`/trainings${params}`),
  });

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees", "active"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/trainings", {
      ...data,
      valid_months: data.valid_months === "" ? null : data.valid_months,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["trainings"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/trainings/${id}`, {
        ...data,
        valid_months: data.valid_months === "" ? null : data.valid_months,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["trainings"] }); setEditTraining(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/trainings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trainings"] }),
  });

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  const FILTERS = [
    { value: "",              label: "Všechna" },
    { value: "valid",         label: "Platná" },
    { value: "expiring_soon", label: "Expirují brzy" },
    { value: "expired",       label: "Expirovaná" },
    { value: "no_expiry",     label: "Bez expirace" },
  ];

  return (
    <div>
      <Header
        title="Školení BOZP/PO"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat školení
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2 flex-wrap">
          {FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setValidityFilter(f.value)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                validityFilter === f.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              )}
            >
              {f.label}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{trainings.length} záznamů</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open("/api/v1/trainings/export/pdf", "_blank")}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            PDF
          </Button>
        </div>

        {/* Tabulka */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-10 animate-pulse bg-gray-100 rounded" />
                ))}
              </div>
            ) : trainings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <GraduationCap className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádná školení</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zaměstnanec</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Školení</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Absolvováno</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Platnost do</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {trainings.map(t => (
                      <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {t.employee_name ?? "—"}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{t.title}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(t.trained_at)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(t.valid_until)}</td>
                        <td className="py-3 px-4">
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            VALIDITY_COLORS[t.validity_status]
                          )}>
                            {VALIDITY_LABELS[t.validity_status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditTraining(t); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Archivovat školení: ${t.title}?`))
                                  archiveMutation.mutate(t.id);
                              }}
                              className="rounded p-1 text-gray-400 hover:text-orange-600 hover:bg-orange-50 transition-colors"
                              title="Archivovat"
                            >
                              <Archive className="h-3.5 w-3.5" />
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

      {/* Dialog: Nové školení */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat školení"
        size="md"
      >
        <TrainingForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          employees={employees}
        />
      </Dialog>

      {/* Dialog: Upravit školení */}
      <Dialog
        open={!!editTraining}
        onClose={() => setEditTraining(null)}
        title={editTraining?.title ?? ""}
        size="md"
      >
        {editTraining && (
          <TrainingForm
            defaultValues={{
              employee_id:   editTraining.employee_id,
              title:         editTraining.title,
              training_type: editTraining.training_type,
              trained_at:    editTraining.trained_at,
              valid_months:  editTraining.valid_months ?? "",
              trainer_name:  editTraining.trainer_name ?? "",
              notes:         editTraining.notes ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editTraining.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            employees={employees}
            isEdit
          />
        )}
      </Dialog>
    </div>
  );
}
