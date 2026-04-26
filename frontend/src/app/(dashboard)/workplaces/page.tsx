"use client";

/**
 * Modul „Provozovny, pracoviště, pozice".
 *
 * Hierarchie:
 *   Plant (provozovna)  — rozbalovací karta
 *     └─ Workplace (pracoviště)
 *         └─ JobPosition (pozice) — každá má 1:1 RiskFactorAssessment
 *
 * CRUD na všech úrovních. RFA se vyplňuje v samostatném dialogu
 * (matrix 13 faktorů × 5 hodnocení) s možností uploadu PDF per faktor.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Pencil, Trash2, ChevronDown, ChevronRight,
  Building2, Briefcase, Factory, ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  Plant, Workplace, JobPosition,
} from "@/types/api";
import { RF_ORDER, RF_LABELS, RISK_RATINGS } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const INPUT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function errMsg(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Chyba serveru";
}

// ── Plant form ─────────────────────────────────────────────────────────────

function PlantForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  error,
}: {
  defaultValues?: Partial<Plant>;
  onSubmit: (data: Partial<Plant>) => void;
  isSubmitting: boolean;
  error: string | null;
}) {
  const [form, setForm] = useState<Partial<Plant>>({
    name: defaultValues?.name ?? "",
    address: defaultValues?.address ?? "",
    city: defaultValues?.city ?? "",
    zip_code: defaultValues?.zip_code ?? "",
    ico: defaultValues?.ico ?? "",
  });

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(form); }}
      className="space-y-3"
    >
      <div className="space-y-1.5">
        <Label htmlFor="name">Název provozovny *</Label>
        <Input
          id="name"
          value={form.name ?? ""}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5 col-span-2">
          <Label htmlFor="address">Adresa</Label>
          <Input
            id="address"
            value={form.address ?? ""}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="city">Město</Label>
          <Input
            id="city"
            value={form.city ?? ""}
            onChange={(e) => setForm({ ...form, city: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zip_code">PSČ</Label>
          <Input
            id="zip_code"
            value={form.zip_code ?? ""}
            onChange={(e) => setForm({ ...form, zip_code: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ico">IČO</Label>
          <Input
            id="ico"
            value={form.ico ?? ""}
            onChange={(e) => setForm({ ...form, ico: e.target.value })}
          />
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── Workplace form ─────────────────────────────────────────────────────────

function WorkplaceForm({
  plantId,
  defaultValues,
  onSubmit,
  isSubmitting,
  error,
}: {
  plantId: string;
  defaultValues?: Partial<Workplace>;
  onSubmit: (data: { plant_id: string; name: string; notes: string | null }) => void;
  isSubmitting: boolean;
  error: string | null;
}) {
  const [name, setName] = useState(defaultValues?.name ?? "");
  const [notes, setNotes] = useState(defaultValues?.notes ?? "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ plant_id: plantId, name, notes: notes || null });
      }}
      className="space-y-3"
    >
      <div className="space-y-1.5">
        <Label htmlFor="wp_name">Název pracoviště *</Label>
        <Input
          id="wp_name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wp_notes">Poznámky</Label>
        <textarea
          id="wp_notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className={cn(INPUT_CLS, "resize-none")}
        />
      </div>
      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      <div className="flex justify-end">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── JobPosition form ──────────────────────────────────────────────────────

function PositionForm({
  workplaceId,
  defaultValues,
  onSubmit,
  isSubmitting,
  error,
}: {
  workplaceId: string;
  defaultValues?: Partial<JobPosition>;
  onSubmit: (data: {
    workplace_id: string; name: string; description: string | null;
    work_category: string | null; medical_exam_period_months: number | null;
  }) => void;
  isSubmitting: boolean;
  error: string | null;
}) {
  const [name, setName] = useState(defaultValues?.name ?? "");
  const [description, setDescription] = useState(defaultValues?.description ?? "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          workplace_id: workplaceId,
          name,
          description: description || null,
          // Kategorie práce a lhůta LP se nyní derivuje automaticky:
          //   - kategorie z RFA (category_proposed)
          //   - lhůta LP z (kategorie + věk zaměstnance) podle vyhlášky 79/2013 Sb.
          work_category: null,
          medical_exam_period_months: null,
        });
      }}
      className="space-y-3"
    >
      <div className="space-y-1.5">
        <Label htmlFor="pos_name">Název pozice *</Label>
        <Input
          id="pos_name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="pos_desc">Popis</Label>
        <textarea
          id="pos_desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className={cn(INPUT_CLS, "resize-none")}
        />
      </div>
      <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
        Kategorie práce se odvozuje z hodnocení rizik (RFA) — vyplníte ji
        v modulu &bdquo;Úroveň rizik na pracovištích&ldquo;. Lhůta lékařské
        prohlídky se vypočítá automaticky podle kategorie a věku zaměstnance
        (vyhláška 79/2013 Sb.).
      </div>
      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      <div className="flex justify-end">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── Workplace-level RFA matrix dialog body ───────────────────────────────
// Hodnocení rizik se nyní eviduje per-pracoviště (workplace) — bulk-update
// propaguje rating na všechny pozice pracoviště. Pozice rizika dědí.
// PDF měření per faktor zde záměrně nejsou — PDF zůstávají per-pozice
// a budou se spravovat samostatně (např. v detailu pozice / RFA dokumentu).

function WorkplaceRfaMatrixBody({
  workplaceId,
  onClose,
}: {
  workplaceId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data, isLoading } = useQuery<{
    workplace_id: string;
    factors: Record<string, string | null>;
  }>({
    queryKey: ["workplace-rfa", workplaceId],
    queryFn: () => api.get(`/workplaces/${workplaceId}/risk-assessment`),
  });

  const updateFactor = useMutation({
    mutationFn: (payload: { factor: string; rating: string | null }) =>
      api.put(`/workplaces/${workplaceId}/risk-assessment`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workplace-rfa", workplaceId] });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => setSaveError(errMsg(err)),
  });

  if (isLoading || !data) {
    return <div className="h-32 animate-pulse bg-gray-50 dark:bg-gray-800 rounded" />;
  }

  const factors = data.factors;

  return (
    <div className="space-y-4">
      <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800
                      dark:bg-blue-900/30 dark:border-blue-700 dark:text-blue-200">
        Hodnocení rizik je definováno na úrovni pracoviště. Změna se propaguje
        na všechny pozice tohoto pracoviště automaticky. Pozice nelze upravovat
        zvlášť — dědí ratingy z pracoviště.
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-300">
              <th className="text-left py-2 px-3">Faktor</th>
              {RISK_RATINGS.map((r) => (
                <th key={r} className="text-center py-2 px-3 w-14">{r}</th>
              ))}
              <th className="text-center py-2 px-3 w-8">—</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
            {RF_ORDER.map((factor) => {
              const currentRating = factors[factor];
              return (
                <tr key={factor}>
                  <td className="py-2 px-3 font-medium text-gray-800 dark:text-gray-100">
                    {RF_LABELS[factor]}
                  </td>
                  {RISK_RATINGS.map((r) => (
                    <td key={r} className="text-center py-1">
                      <input
                        type="radio"
                        name={`rating-${factor}`}
                        checked={currentRating === r}
                        onChange={() => updateFactor.mutate({ factor, rating: r })}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                      />
                    </td>
                  ))}
                  <td className="text-center py-1">
                    <input
                      type="radio"
                      name={`rating-${factor}`}
                      checked={!currentRating}
                      onChange={() => updateFactor.mutate({ factor, rating: null })}
                      className="h-4 w-4 text-gray-400 focus:ring-gray-300"
                      title="Neaplikuje se"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {saveError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {saveError}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <Button onClick={onClose} variant="outline">Zavřít</Button>
      </div>
    </div>
  );
}

// ── Nested: positions under a workplace ───────────────────────────────────

function PositionsTable({
  workplaceId,
  onEditPosition,
  onDeletePosition,
}: {
  workplaceId: string;
  onEditPosition: (jp: JobPosition) => void;
  onDeletePosition: (jp: JobPosition) => void;
}) {
  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["positions", workplaceId],
    queryFn: () => api.get(`/job-positions?workplace_id=${workplaceId}&jp_status=active`),
  });

  if (positions.length === 0) {
    return (
      <div className="text-xs text-gray-400 py-2 pl-8">
        Žádné pozice.
      </div>
    );
  }

  return (
    <div className="pl-8">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-500">
            <th className="text-left py-1 font-medium">Pozice</th>
            <th className="text-left py-1 font-medium w-24">Kategorie</th>
            <th className="text-left py-1 font-medium w-28">Lhůta LP</th>
            <th className="w-32" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {positions.map((jp) => (
            <tr key={jp.id} className="hover:bg-gray-50/50">
              <td className="py-1.5 pr-2 font-medium text-gray-800">
                <Briefcase className="inline h-3.5 w-3.5 mr-1 text-gray-400" />
                {jp.name}
              </td>
              <td className="py-1.5 text-gray-600">
                {jp.effective_category ? (
                  <span className="rounded-full bg-blue-50 text-blue-700 px-2 py-0.5 text-xs font-medium">
                    {jp.effective_category}
                  </span>
                ) : "—"}
              </td>
              <td className="py-1.5 text-gray-500 text-xs">
                {jp.effective_exam_period_months
                  ? `${jp.effective_exam_period_months} měs.`
                  : "—"}
              </td>
              <td className="py-1.5">
                <div className="flex items-center justify-end gap-1">
                  {/*
                    Hodnocení rizik se neřeší per-pozice, ale per-pracoviště
                    (RFA refactor #81). Tlačítko bylo přesunuto na řádek
                    pracoviště ve <WorkplacesSection />. Pozice rizika dědí.
                  */}
                  <button
                    onClick={() => onEditPosition(jp)}
                    className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                    title="Upravit"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => onDeletePosition(jp)}
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
  );
}

function WorkplacesSection({
  plantId,
  onEditWp,
  onDeleteWp,
  onAddPos,
  onEditPos,
  onDeletePos,
  onOpenWorkplaceRfa,
}: {
  plantId: string;
  onEditWp: (wp: Workplace) => void;
  onDeleteWp: (wp: Workplace) => void;
  onAddPos: (workplaceId: string) => void;
  onEditPos: (jp: JobPosition) => void;
  onDeletePos: (jp: JobPosition) => void;
  onOpenWorkplaceRfa: (wp: Workplace) => void;
}) {
  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces", plantId],
    queryFn: () => api.get(`/workplaces?plant_id=${plantId}&wp_status=active`),
  });

  if (workplaces.length === 0) {
    return (
      <div className="text-xs text-gray-400 py-2 pl-6">
        Žádná pracoviště. Přidejte tlačítkem &bdquo;Pracoviště&ldquo; v řádku provozovny.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {workplaces.map((wp) => (
        <div key={wp.id} className="pl-6 border-l-2 border-gray-100">
          <div className="flex items-center justify-between py-1.5">
            <div className="flex items-center gap-2">
              <Factory className="h-4 w-4 text-gray-400" />
              <span className="font-medium text-gray-800">{wp.name}</span>
              {wp.notes && (
                <span className="text-xs text-gray-400">· {wp.notes}</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => onAddPos(wp.id)}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                <Plus className="h-3 w-3" /> Pozice
              </button>
              <button
                onClick={() => onOpenWorkplaceRfa(wp)}
                className="rounded p-1 text-gray-400 hover:text-emerald-600 hover:bg-emerald-50"
                title="Hodnocení rizik (per pracoviště)"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => onEditWp(wp)}
                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                title="Upravit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => onDeleteWp(wp)}
                className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                title="Archivovat"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <PositionsTable
            workplaceId={wp.id}
            onEditPosition={onEditPos}
            onDeletePosition={onDeletePos}
          />
        </div>
      ))}
    </div>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────

export default function WorkplacesPage() {
  const qc = useQueryClient();
  const [expandedPlants, setExpandedPlants] = useState<Set<string>>(new Set());

  const [plantModal, setPlantModal] = useState<{ mode: "create" | "edit"; plant?: Plant } | null>(null);
  const [wpModal, setWpModal] = useState<{ mode: "create" | "edit"; plantId: string; wp?: Workplace } | null>(null);
  const [posModal, setPosModal] = useState<{ mode: "create" | "edit"; workplaceId: string; jp?: JobPosition } | null>(null);
  const [rfaModal, setRfaModal] = useState<Workplace | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: plants = [], isLoading } = useQuery<Plant[]>({
    queryKey: ["plants", "active"],
    queryFn: () => api.get("/plants?plant_status=active"),
  });

  const createPlant = useMutation({
    mutationFn: (data: Partial<Plant>) => api.post("/plants", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plants"] });
      setPlantModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const updatePlant = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Plant> }) =>
      api.patch(`/plants/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plants"] });
      setPlantModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const deletePlant = useMutation({
    mutationFn: (id: string) => api.delete(`/plants/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plants"] }),
  });

  const createWp = useMutation({
    mutationFn: (data: { plant_id: string; name: string; notes: string | null }) =>
      api.post("/workplaces", data),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["workplaces", vars.plant_id] });
      setWpModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const updateWp = useMutation({
    mutationFn: ({ id, data, plantId }: { id: string; data: Partial<Workplace>; plantId: string }) =>
      api.patch(`/workplaces/${id}`, data).then(() => plantId),
    onSuccess: (plantId) => {
      qc.invalidateQueries({ queryKey: ["workplaces", plantId] });
      setWpModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const deleteWp = useMutation({
    mutationFn: ({ id, plantId }: { id: string; plantId: string }) =>
      api.delete(`/workplaces/${id}`).then(() => plantId),
    onSuccess: (plantId) => qc.invalidateQueries({ queryKey: ["workplaces", plantId] }),
  });

  const createPos = useMutation({
    mutationFn: (data: {
      workplace_id: string; name: string; description: string | null;
      work_category: string | null; medical_exam_period_months: number | null;
    }) => api.post("/job-positions", data),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["positions", vars.workplace_id] });
      setPosModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const updatePos = useMutation({
    mutationFn: ({ id, data, workplaceId }: {
      id: string; data: Partial<JobPosition>; workplaceId: string;
    }) => api.patch(`/job-positions/${id}`, data).then(() => workplaceId),
    onSuccess: (workplaceId) => {
      qc.invalidateQueries({ queryKey: ["positions", workplaceId] });
      setPosModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });
  const deletePos = useMutation({
    mutationFn: ({ id, workplaceId }: { id: string; workplaceId: string }) =>
      api.delete(`/job-positions/${id}`).then(() => workplaceId),
    onSuccess: (workplaceId) => qc.invalidateQueries({ queryKey: ["positions", workplaceId] }),
  });

  function toggleExpanded(plantId: string) {
    const next = new Set(expandedPlants);
    if (next.has(plantId)) next.delete(plantId);
    else next.add(plantId);
    setExpandedPlants(next);
  }

  return (
    <div>
      <Header
        title="Provozovny, pracoviště, pozice"
        actions={
          <Button
            size="sm"
            onClick={() => { setFormError(null); setPlantModal({ mode: "create" }); }}
          >
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat provozovnu
          </Button>
        }
      />

      <div className="p-6 space-y-3">
        {isLoading ? (
          <div className="h-20 animate-pulse bg-gray-50 rounded" />
        ) : plants.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-gray-400 text-sm">
              Žádné provozovny. Začněte přidáním první.
            </CardContent>
          </Card>
        ) : (
          plants.map((plant) => {
            const expanded = expandedPlants.has(plant.id);
            return (
              <Card key={plant.id}>
                <CardContent className="p-0">
                  <div className="flex items-center justify-between px-4 py-3 hover:bg-gray-50/40">
                    <button
                      onClick={() => toggleExpanded(plant.id)}
                      className="flex items-center gap-2 text-left flex-1"
                    >
                      {expanded
                        ? <ChevronDown className="h-4 w-4 text-gray-400" />
                        : <ChevronRight className="h-4 w-4 text-gray-400" />}
                      <Building2 className="h-5 w-5 text-blue-500" />
                      <div>
                        <div className="font-semibold text-gray-900">{plant.name}</div>
                        <div className="text-xs text-gray-500">
                          {[plant.address, plant.city, plant.zip_code].filter(Boolean).join(", ") || "bez adresy"}
                          {plant.ico && <span className="ml-2">· IČO {plant.ico}</span>}
                        </div>
                      </div>
                    </button>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { setFormError(null); setWpModal({ mode: "create", plantId: plant.id }); }}
                        className="text-xs text-blue-600 hover:underline flex items-center gap-1 mr-1"
                      >
                        <Plus className="h-3 w-3" /> Pracoviště
                      </button>
                      <button
                        onClick={() => { setFormError(null); setPlantModal({ mode: "edit", plant }); }}
                        className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                        title="Upravit"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Archivovat provozovnu ${plant.name}?`))
                            deletePlant.mutate(plant.id);
                        }}
                        className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                        title="Archivovat"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {expanded && (
                    <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                      <WorkplacesSection
                        plantId={plant.id}
                        onEditWp={(wp) => {
                          setFormError(null);
                          setWpModal({ mode: "edit", plantId: plant.id, wp });
                        }}
                        onDeleteWp={(wp) => {
                          if (confirm(`Archivovat pracoviště ${wp.name}?`))
                            deleteWp.mutate({ id: wp.id, plantId: plant.id });
                        }}
                        onAddPos={(workplaceId) => {
                          setFormError(null);
                          setPosModal({ mode: "create", workplaceId });
                        }}
                        onEditPos={(jp) => {
                          setFormError(null);
                          setPosModal({ mode: "edit", workplaceId: jp.workplace_id, jp });
                        }}
                        onDeletePos={(jp) => {
                          if (confirm(`Archivovat pozici ${jp.name}?`))
                            deletePos.mutate({ id: jp.id, workplaceId: jp.workplace_id });
                        }}
                        onOpenWorkplaceRfa={(wp) => setRfaModal(wp)}
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Plant dialog */}
      <Dialog
        open={!!plantModal}
        onClose={() => { setPlantModal(null); setFormError(null); }}
        title={plantModal?.mode === "edit" ? `Upravit: ${plantModal.plant?.name}` : "Přidat provozovnu"}
        size="md"
      >
        {plantModal && (
          <PlantForm
            defaultValues={plantModal.plant}
            onSubmit={(data) => {
              if (plantModal.mode === "edit" && plantModal.plant) {
                updatePlant.mutate({ id: plantModal.plant.id, data });
              } else {
                createPlant.mutate(data);
              }
            }}
            isSubmitting={createPlant.isPending || updatePlant.isPending}
            error={formError}
          />
        )}
      </Dialog>

      {/* Workplace dialog */}
      <Dialog
        open={!!wpModal}
        onClose={() => { setWpModal(null); setFormError(null); }}
        title={wpModal?.mode === "edit" ? "Upravit pracoviště" : "Přidat pracoviště"}
        size="md"
      >
        {wpModal && (
          <WorkplaceForm
            plantId={wpModal.plantId}
            defaultValues={wpModal.wp}
            onSubmit={(data) => {
              if (wpModal.mode === "edit" && wpModal.wp) {
                updateWp.mutate({
                  id: wpModal.wp.id,
                  data: { name: data.name, notes: data.notes },
                  plantId: wpModal.plantId,
                });
              } else {
                createWp.mutate(data);
              }
            }}
            isSubmitting={createWp.isPending || updateWp.isPending}
            error={formError}
          />
        )}
      </Dialog>

      {/* Position dialog */}
      <Dialog
        open={!!posModal}
        onClose={() => { setPosModal(null); setFormError(null); }}
        title={posModal?.mode === "edit" ? "Upravit pozici" : "Přidat pozici"}
        size="md"
      >
        {posModal && (
          <PositionForm
            workplaceId={posModal.workplaceId}
            defaultValues={posModal.jp}
            onSubmit={(data) => {
              if (posModal.mode === "edit" && posModal.jp) {
                updatePos.mutate({
                  id: posModal.jp.id,
                  data,
                  workplaceId: posModal.workplaceId,
                });
              } else {
                createPos.mutate(data);
              }
            }}
            isSubmitting={createPos.isPending || updatePos.isPending}
            error={formError}
          />
        )}
      </Dialog>

      {/* RFA matrix dialog (per-workplace) */}
      <Dialog
        open={!!rfaModal}
        onClose={() => setRfaModal(null)}
        title={rfaModal ? `Hodnocení rizik: ${rfaModal.name}` : ""}
        size="lg"
      >
        {rfaModal && (
          <WorkplaceRfaMatrixBody
            workplaceId={rfaModal.id}
            onClose={() => setRfaModal(null)}
          />
        )}
      </Dialog>
    </div>
  );
}
