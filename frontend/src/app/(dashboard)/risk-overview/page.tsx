"use client";

/**
 * Modul „Úroveň rizik na pracovištích".
 *
 * Hierarchický přehled: Plant → Workplace → kategorie práce nejvyšší pozice.
 * Editace kategorie konkrétní pozice se otevírá v dialogu s rychlou volbou
 * (1/2/2R/3/4) a propisuje se do JobPosition.work_category.
 *
 * Pro detailní RFA matrix (13 faktorů × 5 hodnocení) zachováváme tlačítko,
 * které přesměruje uživatele do modulu Provozovny.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, Factory, Briefcase, ShieldCheck,
  Pencil, ExternalLink, AlertTriangle,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Plant, Workplace, JobPosition } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const CATEGORIES = ["1", "2", "2R", "3", "4"] as const;
type Category = typeof CATEGORIES[number];

const CATEGORY_COLORS: Record<string, string> = {
  "1":  "bg-green-100 text-green-700 border-green-300",
  "2":  "bg-yellow-100 text-yellow-700 border-yellow-300",
  "2R": "bg-orange-100 text-orange-700 border-orange-300",
  "3":  "bg-red-100 text-red-700 border-red-300",
  "4":  "bg-rose-200 text-rose-800 border-rose-400",
};

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  "1":  "Práce minimálního rizika — nepředstavuje riziko ohrožení zdraví",
  "2":  "Práce, kde lze předpokládat, že nepřekročí hygienické limity",
  "2R": "Riziková práce — pevné hygienické limity překročeny ojediněle",
  "3":  "Práce nad hygienické limity — nutná kompenzační opatření",
  "4":  "Vysoké riziko ohrožení zdraví — i přes opatření",
};

function maxCategory(positions: JobPosition[]): Category | null {
  const order = ["1", "2", "2R", "3", "4"];
  let highest: Category | null = null;
  for (const p of positions) {
    if (!p.work_category) continue;
    const idx = order.indexOf(p.work_category);
    const curIdx = highest ? order.indexOf(highest) : -1;
    if (idx > curIdx) highest = p.work_category as Category;
  }
  return highest;
}

// ── Editor kategorie pozice ──────────────────────────────────────────────────

function CategoryEditDialog({
  position, onClose,
}: {
  position: JobPosition | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Category | "">(
    (position?.work_category as Category) ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (work_category: string | null) =>
      api.patch(`/job-positions/${position?.id}`, { work_category }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job-positions"] });
      qc.invalidateQueries({ queryKey: ["risk-overview-positions"] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  if (!position) return null;

  return (
    <Dialog open={!!position} onClose={onClose} title={`Kategorie práce — ${position.name}`} size="md">
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Vyberte kategorii práce dle NV 361/2007 Sb. Kategorie se použije pro
          výpočet lhůt periodických prohlídek a doporučení odborných vyšetření.
        </p>

        <div className="grid grid-cols-1 gap-2">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelected(cat)}
              className={cn(
                "flex items-start gap-3 rounded-md border p-3 text-left transition-all",
                selected === cat
                  ? `${CATEGORY_COLORS[cat]} ring-2 ring-blue-500`
                  : "border-gray-200 bg-white hover:border-gray-300",
              )}
            >
              <span className={cn(
                "shrink-0 inline-flex items-center justify-center rounded-full px-2.5 py-1 text-sm font-bold border",
                CATEGORY_COLORS[cat],
              )}>
                {cat}
              </span>
              <span className="text-xs text-gray-700 leading-snug">
                {CATEGORY_DESCRIPTIONS[cat]}
              </span>
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setSelected("")}
          className="text-xs text-gray-500 hover:text-gray-700 underline"
        >
          Vymazat kategorii
        </button>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Zrušit</Button>
          <Button
            onClick={() => mutation.mutate(selected || null)}
            loading={mutation.isPending}
          >
            Uložit
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

// ── Workplace card ───────────────────────────────────────────────────────────

function WorkplaceCard({
  workplace,
  positions,
  onEditPosition,
}: {
  workplace: Workplace;
  positions: JobPosition[];
  onEditPosition: (p: JobPosition) => void;
}) {
  const maxCat = maxCategory(positions);

  return (
    <div className="rounded-md border border-gray-200 bg-white p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Briefcase className="h-4 w-4 text-blue-600 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{workplace.name}</p>
            {workplace.notes && (
              <p className="text-xs text-gray-500 truncate">{workplace.notes}</p>
            )}
          </div>
        </div>
        {maxCat ? (
          <Tooltip label={`Nejvyšší kategorie rizika na tomto pracovišti: ${CATEGORY_DESCRIPTIONS[maxCat]}`}>
            <span className={cn(
              "shrink-0 inline-flex items-center justify-center rounded-full px-2.5 py-1 text-xs font-bold border",
              CATEGORY_COLORS[maxCat],
            )}>
              kat. {maxCat}
            </span>
          </Tooltip>
        ) : (
          <Tooltip label="Žádná pozice nemá nastavenou kategorii práce">
            <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-gray-100 text-gray-500 px-2.5 py-1 text-xs font-medium border border-gray-300">
              <AlertTriangle className="h-3 w-3" /> bez kat.
            </span>
          </Tooltip>
        )}
      </div>

      {positions.length === 0 ? (
        <p className="text-xs text-gray-400 italic pl-6">
          Žádné pozice. Přidejte je v modulu Provozovny.
        </p>
      ) : (
        <ul className="pl-6 space-y-1">
          {positions.map(p => (
            <li key={p.id} className="flex items-center justify-between gap-2">
              <span className="text-xs text-gray-700 truncate">{p.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                {p.work_category ? (
                  <span className={cn(
                    "inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-bold border",
                    CATEGORY_COLORS[p.work_category],
                  )}>
                    {p.work_category}
                  </span>
                ) : (
                  <span className="text-[10px] text-gray-400">—</span>
                )}
                <Tooltip label="Změnit kategorii práce této pozice">
                  <button
                    onClick={() => onEditPosition(p)}
                    className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                    aria-label="Upravit kategorii"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                </Tooltip>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────────

export default function RiskOverviewPage() {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [editPosition, setEditPosition] = useState<JobPosition | null>(null);

  const { data: plants = [], isLoading: plantsLoading } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants?plant_status=active"),
  });

  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces"],
    queryFn: () => api.get("/workplaces?wp_status=active"),
  });

  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["risk-overview-positions"],
    queryFn: () => api.get("/job-positions?jp_status=active"),
  });

  function toggle(plantId: string) {
    setExpanded(prev => ({ ...prev, [plantId]: !prev[plantId] }));
  }

  function expandAll() {
    setExpanded(Object.fromEntries(plants.map(p => [p.id, true])));
  }

  function workplacesFor(plantId: string) {
    return workplaces.filter(w => w.plant_id === plantId);
  }

  function positionsFor(workplaceId: string) {
    return positions.filter(p => p.workplace_id === workplaceId);
  }

  // Souhrn — kolik pracovišť celkem, kolik s kategorií ≥ 3, kolik bez kat.
  const summaryCounts = workplaces.reduce(
    (acc, w) => {
      const cat = maxCategory(positionsFor(w.id));
      acc.total++;
      if (cat === "3" || cat === "4") acc.high++;
      else if (cat === null) acc.unset++;
      return acc;
    },
    { total: 0, high: 0, unset: 0 },
  );

  return (
    <div>
      <Header
        title="Úroveň rizik na pracovištích"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={expandAll}>
              Rozbalit vše
            </Button>
            <Link href="/workplaces">
              <Button size="sm">
                <ExternalLink className="h-4 w-4 mr-1.5" />
                Detailní RFA matrix
              </Button>
            </Link>
          </div>
        }
      />

      <div className="p-6 space-y-4">
        {/* Souhrn */}
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Celkem pracovišť</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{summaryCounts.total}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Riziková (kat. 3+4)</p>
              <p className="text-2xl font-bold text-red-700 mt-1">{summaryCounts.high}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Bez kategorie</p>
              <p className="text-2xl font-bold text-amber-600 mt-1">{summaryCounts.unset}</p>
            </CardContent>
          </Card>
        </div>

        {/* Hierarchie */}
        {plantsLoading ? (
          <Card>
            <CardContent className="p-6">
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-12 animate-pulse bg-gray-50 rounded" />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : plants.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center text-gray-400">
              <Factory className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Žádné provozovny</p>
              <p className="text-xs mt-1">
                Přidejte provozovny a pracoviště v modulu &bdquo;Provozovny&ldquo;.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {plants.map(plant => {
              const wps = workplacesFor(plant.id);
              const isOpen = expanded[plant.id] ?? true;
              return (
                <Card key={plant.id}>
                  <CardContent className="p-0">
                    <button
                      onClick={() => toggle(plant.id)}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 text-left"
                    >
                      {isOpen ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
                      <Factory className="h-5 w-5 text-blue-600" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-gray-900">{plant.name}</p>
                        {(plant.address || plant.city) && (
                          <p className="text-xs text-gray-500">
                            {[plant.address, plant.zip_code, plant.city].filter(Boolean).join(", ")}
                          </p>
                        )}
                      </div>
                      <span className="text-xs text-gray-400">
                        {wps.length} {wps.length === 1 ? "pracoviště" : "pracovišť"}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="border-t border-gray-100 p-4 bg-gray-50/50">
                        {wps.length === 0 ? (
                          <p className="text-xs text-gray-400 italic">Žádná pracoviště</p>
                        ) : (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {wps.map(w => (
                              <WorkplaceCard
                                key={w.id}
                                workplace={w}
                                positions={positionsFor(w.id)}
                                onEditPosition={setEditPosition}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          <ShieldCheck className="h-4 w-4 inline mr-1.5 -mt-0.5" />
          Kategorie 1/2 jsou nerizikové, 2R/3/4 vyžadují periodickou
          pracovnělékařskou prohlídku, odborná vyšetření (audiometrie, spirometrie, …)
          a OOPP. Detailní hodnocení 13 rizikových faktorů (RFA matrix) najdete
          v modulu Provozovny.
        </div>
      </div>

      <CategoryEditDialog
        position={editPosition}
        onClose={() => setEditPosition(null)}
      />
    </div>
  );
}
