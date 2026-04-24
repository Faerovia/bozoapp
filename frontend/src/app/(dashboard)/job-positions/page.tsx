"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Briefcase, Plus, Pencil, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { JobPosition } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";

// ── Konstanty ─────────────────────────────────────────────────────────────────

const WORK_CATEGORIES = [
  { value: "",   label: "— Nevybráno —" },
  { value: "1",  label: "Kategorie 1 – bez rizika" },
  { value: "2",  label: "Kategorie 2 – malé riziko" },
  { value: "2R", label: "Kategorie 2R – rizikový faktor" },
  { value: "3",  label: "Kategorie 3 – riziková práce" },
  { value: "4",  label: "Kategorie 4 – riziková práce (nejvyšší)" },
];

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const CATEGORY_COLORS: Record<string, string> = {
  "1":  "bg-green-100 text-green-700",
  "2":  "bg-blue-100 text-blue-700",
  "2R": "bg-amber-100 text-amber-700",
  "3":  "bg-orange-100 text-orange-700",
  "4":  "bg-red-100 text-red-700",
};

// ── Schéma ────────────────────────────────────────────────────────────────────

const schema = z.object({
  name:                        z.string().min(1, "Název je povinný"),
  description:                 z.string().optional(),
  work_category:               z.string().optional(),
  medical_exam_period_months:  z.coerce.number().int().positive().optional().or(z.literal("")),
  effective_exam_period_months: z.coerce.number().int().positive().optional().or(z.literal("")),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ──────────────────────────────────────────────────────────────────

function JobPositionForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (d: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues,
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="jp-name">Název pozice *</Label>
        <Input id="jp-name" {...register("name")} placeholder="např. Svářeč MIG/MAG" />
        {errors.name && <p className="text-xs text-red-600">{errors.name.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="jp-desc">Popis</Label>
        <textarea
          id="jp-desc"
          {...register("description")}
          rows={2}
          placeholder="Stručný popis náplně práce a rizikových faktorů"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="jp-cat">Kategorie práce (dle zák. 258/2000 Sb.)</Label>
        <select id="jp-cat" {...register("work_category")} className={SELECT_CLS}>
          {WORK_CATEGORIES.map(c => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="jp-period">Periodicita prohlídek (měs.)</Label>
          <Input
            id="jp-period"
            type="number"
            min={1}
            max={120}
            placeholder="prázdné = bez lhůty"
            {...register("medical_exam_period_months")}
          />
          <p className="text-xs text-gray-400">Zákonná lhůta dle kat. práce</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="jp-eff">Platnost prohlídky (měs.)</Label>
          <Input
            id="jp-eff"
            type="number"
            min={1}
            max={120}
            placeholder="prázdné = bez platnosti"
            {...register("effective_exam_period_months")}
          />
          <p className="text-xs text-gray-400">Dle § 11 vyhl. 79/2013 Sb.</p>
        </div>
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

export default function JobPositionsPage() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen]         = useState(false);
  const [editPosition, setEditPosition]     = useState<JobPosition | null>(null);
  const [serverError, setServerError]       = useState<string | null>(null);

  const { data: positions = [], isLoading } = useQuery<JobPosition[]>({
    queryKey: ["job-positions"],
    queryFn:  () => api.get("/job-positions"),
  });

  const createMutation = useMutation({
    mutationFn: (d: FormData) => api.post("/job-positions", {
      ...d,
      work_category:               d.work_category || null,
      medical_exam_period_months:  d.medical_exam_period_months === "" ? null : d.medical_exam_period_months,
      effective_exam_period_months: d.effective_exam_period_months === "" ? null : d.effective_exam_period_months,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["job-positions"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, d }: { id: string; d: Partial<FormData> }) => api.patch(`/job-positions/${id}`, {
      ...d,
      work_category:               d.work_category || null,
      medical_exam_period_months:  d.medical_exam_period_months === "" ? null : d.medical_exam_period_months,
      effective_exam_period_months: d.effective_exam_period_months === "" ? null : d.effective_exam_period_months,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["job-positions"] }); setEditPosition(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/job-positions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["job-positions"] }),
  });

  return (
    <div>
      <Header
        title="Pracovní pozice"
        actions={
          <Button size="sm" onClick={() => { setServerError(null); setCreateOpen(true); }}>
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat pozici
          </Button>
        }
      />

      <div className="p-6">
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-10 animate-pulse bg-gray-100 rounded" />
                ))}
              </div>
            ) : positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Briefcase className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné pracovní pozice</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Název pozice</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Kategorie</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Periodicita prohlídky</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Platnost prohlídky</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {positions.map(p => (
                      <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-medium text-gray-900">{p.name}</div>
                          {p.description && (
                            <div className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{p.description}</div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          {p.work_category ? (
                            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CATEGORY_COLORS[p.work_category] ?? "bg-gray-100 text-gray-600"}`}>
                              Kat. {p.work_category}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          {p.medical_exam_period_months ? `${p.medical_exam_period_months} měs.` : "—"}
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          {p.effective_exam_period_months ? `${p.effective_exam_period_months} měs.` : "—"}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditPosition(p); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Smazat pozici: ${p.name}?`))
                                  deleteMutation.mutate(p.id);
                              }}
                              className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                              title="Smazat"
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

      {/* Dialog: Nová pozice */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat pracovní pozici"
        size="md"
      >
        <JobPositionForm
          onSubmit={(d) => { setServerError(null); createMutation.mutate(d); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
        />
      </Dialog>

      {/* Dialog: Upravit pozici */}
      <Dialog
        open={!!editPosition}
        onClose={() => setEditPosition(null)}
        title={editPosition?.name ?? ""}
        size="md"
      >
        {editPosition && (
          <JobPositionForm
            defaultValues={{
              name:                        editPosition.name,
              description:                 editPosition.description ?? "",
              work_category:               editPosition.work_category ?? "",
              medical_exam_period_months:  editPosition.medical_exam_period_months ?? "",
              effective_exam_period_months: editPosition.effective_exam_period_months ?? "",
            }}
            onSubmit={(d) => {
              setServerError(null);
              updateMutation.mutate({ id: editPosition.id, d });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>
    </div>
  );
}
