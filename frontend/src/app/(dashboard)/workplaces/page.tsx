"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2, MapPin, Plus, Pencil, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Plant, Workplace } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";

// ── Schemata ──────────────────────────────────────────────────────────────────

const plantSchema = z.object({
  name:    z.string().min(1, "Název je povinný"),
  address: z.string().optional(),
  city:    z.string().optional(),
});

const workplaceSchema = z.object({
  plant_id: z.string().uuid("Vyberte provozovnu"),
  name:     z.string().min(1, "Název je povinný"),
  notes:    z.string().optional(),
});

type PlantForm     = z.infer<typeof plantSchema>;
type WorkplaceForm = z.infer<typeof workplaceSchema>;

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Plant dialog ──────────────────────────────────────────────────────────────

function PlantFormDialog({
  open,
  onClose,
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  isEdit,
}: {
  open: boolean;
  onClose: () => void;
  defaultValues?: Partial<PlantForm>;
  onSubmit: (d: PlantForm) => void;
  isSubmitting: boolean;
  serverError: string | null;
  isEdit?: boolean;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<PlantForm>({
    resolver: zodResolver(plantSchema),
    defaultValues,
  });

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Upravit provozovnu" : "Nová provozovna"} size="sm">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="p-name">Název *</Label>
          <Input id="p-name" {...register("name")} placeholder="např. Sklad Praha" />
          {errors.name && <p className="text-xs text-red-600">{errors.name.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-address">Adresa</Label>
          <Input id="p-address" {...register("address")} placeholder="Ulice a číslo" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-city">Město</Label>
          <Input id="p-city" {...register("city")} placeholder="Praha" />
        </div>
        {serverError && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{serverError}</div>
        )}
        <div className="flex justify-end pt-2">
          <Button type="submit" loading={isSubmitting}>Uložit</Button>
        </div>
      </form>
    </Dialog>
  );
}

// ── Workplace dialog ──────────────────────────────────────────────────────────

function WorkplaceFormDialog({
  open,
  onClose,
  plants,
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  isEdit,
}: {
  open: boolean;
  onClose: () => void;
  plants: Plant[];
  defaultValues?: Partial<WorkplaceForm>;
  onSubmit: (d: WorkplaceForm) => void;
  isSubmitting: boolean;
  serverError: string | null;
  isEdit?: boolean;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<WorkplaceForm>({
    resolver: zodResolver(workplaceSchema),
    defaultValues,
  });

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Upravit pracoviště" : "Nové pracoviště"} size="sm">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="w-plant">Provozovna *</Label>
          <select id="w-plant" {...register("plant_id")} className={SELECT_CLS}>
            <option value="">— Vyberte provozovnu —</option>
            {plants.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {errors.plant_id && <p className="text-xs text-red-600">{errors.plant_id.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="w-name">Název pracoviště *</Label>
          <Input id="w-name" {...register("name")} placeholder="např. Montážní hala A" />
          {errors.name && <p className="text-xs text-red-600">{errors.name.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="w-notes">Poznámky</Label>
          <textarea
            id="w-notes"
            {...register("notes")}
            rows={2}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>
        {serverError && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{serverError}</div>
        )}
        <div className="flex justify-end pt-2">
          <Button type="submit" loading={isSubmitting}>Uložit</Button>
        </div>
      </form>
    </Dialog>
  );
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function WorkplacesPage() {
  const qc = useQueryClient();

  // Plants state
  const [plantCreate, setPlantCreate]         = useState(false);
  const [editPlant, setEditPlant]             = useState<Plant | null>(null);
  const [plantError, setPlantError]           = useState<string | null>(null);

  // Workplaces state
  const [workplaceCreate, setWorkplaceCreate] = useState(false);
  const [editWorkplace, setEditWorkplace]     = useState<Workplace | null>(null);
  const [workplaceError, setWorkplaceError]   = useState<string | null>(null);

  // ── Queries ────────────────────────────────────────────────────────────────

  const { data: plants = [], isLoading: plantsLoading } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/workplaces/plants"),
  });

  const { data: workplaces = [], isLoading: workplacesLoading } = useQuery<Workplace[]>({
    queryKey: ["workplaces"],
    queryFn: () => api.get("/workplaces"),
  });

  // Helper: plant name lookup
  const plantName = (id: string) => plants.find(p => p.id === id)?.name ?? "—";

  // ── Plant mutations ────────────────────────────────────────────────────────

  const createPlant = useMutation({
    mutationFn: (d: PlantForm) => api.post("/workplaces/plants", d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["plants"] }); setPlantCreate(false); },
    onError: (err) => setPlantError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updatePlant = useMutation({
    mutationFn: ({ id, d }: { id: string; d: Partial<PlantForm> }) => api.patch(`/workplaces/plants/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["plants"] }); setEditPlant(null); },
    onError: (err) => setPlantError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deletePlant = useMutation({
    mutationFn: (id: string) => api.delete(`/workplaces/plants/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plants"] }),
  });

  // ── Workplace mutations ────────────────────────────────────────────────────

  const createWorkplace = useMutation({
    mutationFn: (d: WorkplaceForm) => api.post("/workplaces", d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workplaces"] }); setWorkplaceCreate(false); },
    onError: (err) => setWorkplaceError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateWorkplace = useMutation({
    mutationFn: ({ id, d }: { id: string; d: Partial<WorkplaceForm> }) => api.patch(`/workplaces/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workplaces"] }); setEditWorkplace(null); },
    onError: (err) => setWorkplaceError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteWorkplace = useMutation({
    mutationFn: (id: string) => api.delete(`/workplaces/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workplaces"] }),
  });

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      <Header title="Provozovny a pracoviště" />

      <div className="p-6 space-y-6">

        {/* ── Provozovny ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-gray-400" />
              <h2 className="text-sm font-semibold text-gray-700">Provozovny</h2>
              <span className="text-xs text-gray-400">{plants.length} záznamy</span>
            </div>
            <Button size="sm" onClick={() => { setPlantError(null); setPlantCreate(true); }}>
              <Plus className="h-4 w-4 mr-1.5" />
              Přidat provozovnu
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              {plantsLoading ? (
                <div className="space-y-2 p-4">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-10 animate-pulse bg-gray-100 rounded" />
                  ))}
                </div>
              ) : plants.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-gray-400">
                  <Building2 className="h-8 w-8 mb-2 opacity-30" />
                  <p className="text-sm">Žádné provozovny</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100 bg-gray-50">
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Název</th>
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Adresa</th>
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Město</th>
                        <th className="py-3 px-4" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {plants.map(p => (
                        <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                          <td className="py-3 px-4 font-medium text-gray-900">{p.name}</td>
                          <td className="py-3 px-4 text-gray-600">{p.address ?? "—"}</td>
                          <td className="py-3 px-4 text-gray-600">{p.city ?? "—"}</td>
                          <td className="py-3 px-4">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => { setPlantError(null); setEditPlant(p); }}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                title="Upravit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => {
                                  if (confirm(`Smazat provozovnu: ${p.name}?`))
                                    deletePlant.mutate(p.id);
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
        </section>

        {/* ── Pracoviště ── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-gray-400" />
              <h2 className="text-sm font-semibold text-gray-700">Pracoviště</h2>
              <span className="text-xs text-gray-400">{workplaces.length} záznamy</span>
            </div>
            <Button size="sm" onClick={() => { setWorkplaceError(null); setWorkplaceCreate(true); }}>
              <Plus className="h-4 w-4 mr-1.5" />
              Přidat pracoviště
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              {workplacesLoading ? (
                <div className="space-y-2 p-4">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-10 animate-pulse bg-gray-100 rounded" />
                  ))}
                </div>
              ) : workplaces.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-gray-400">
                  <MapPin className="h-8 w-8 mb-2 opacity-30" />
                  <p className="text-sm">Žádná pracoviště</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100 bg-gray-50">
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Pracoviště</th>
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Provozovna</th>
                        <th className="text-left py-3 px-4 font-medium text-gray-500">Poznámky</th>
                        <th className="py-3 px-4" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {workplaces.map(w => (
                        <tr key={w.id} className="hover:bg-gray-50 transition-colors">
                          <td className="py-3 px-4 font-medium text-gray-900">{w.name}</td>
                          <td className="py-3 px-4 text-gray-600">{plantName(w.plant_id)}</td>
                          <td className="py-3 px-4 text-gray-500 text-xs max-w-xs truncate">{w.notes ?? "—"}</td>
                          <td className="py-3 px-4">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => { setWorkplaceError(null); setEditWorkplace(w); }}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                title="Upravit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => {
                                  if (confirm(`Smazat pracoviště: ${w.name}?`))
                                    deleteWorkplace.mutate(w.id);
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
        </section>
      </div>

      {/* Dialogy – Provozovny */}
      <PlantFormDialog
        open={plantCreate}
        onClose={() => setPlantCreate(false)}
        onSubmit={(d) => { setPlantError(null); createPlant.mutate(d); }}
        isSubmitting={createPlant.isPending}
        serverError={plantError}
      />
      <PlantFormDialog
        open={!!editPlant}
        onClose={() => setEditPlant(null)}
        defaultValues={editPlant ?? undefined}
        onSubmit={(d) => { setPlantError(null); updatePlant.mutate({ id: editPlant!.id, d }); }}
        isSubmitting={updatePlant.isPending}
        serverError={plantError}
        isEdit
      />

      {/* Dialogy – Pracoviště */}
      <WorkplaceFormDialog
        open={workplaceCreate}
        onClose={() => setWorkplaceCreate(false)}
        plants={plants}
        onSubmit={(d) => { setWorkplaceError(null); createWorkplace.mutate(d); }}
        isSubmitting={createWorkplace.isPending}
        serverError={workplaceError}
      />
      <WorkplaceFormDialog
        open={!!editWorkplace}
        onClose={() => setEditWorkplace(null)}
        plants={plants}
        defaultValues={editWorkplace ? { plant_id: editWorkplace.plant_id, name: editWorkplace.name, notes: editWorkplace.notes ?? "" } : undefined}
        onSubmit={(d) => { setWorkplaceError(null); updateWorkplace.mutate({ id: editWorkplace!.id, d }); }}
        isSubmitting={updateWorkplace.isPending}
        serverError={workplaceError}
        isEdit
      />
    </div>
  );
}
