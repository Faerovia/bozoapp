"use client";

/**
 * Modul „Úroveň rizik na pracovištích".
 *
 * Hierarchický přehled: Plant → Workplace → Position → 13 rizikových faktorů.
 * Pro každou pozici je k dispozici interaktivní matrix 13×5 (faktor × rating).
 * Úroveň rizika pracoviště = maximum kategorií (category_proposed) ze všech
 * jeho pozic. Úroveň provozovny = maximum všech pracovišť.
 *
 * RFA se vytvoří automaticky při prvním kliknutí na rating, pokud pro pozici
 * ještě neexistuje. Změna ratingu propisuje přes PATCH /risk-factors/{id}.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, Factory, Briefcase, ShieldCheck,
  ExternalLink, AlertTriangle, Loader2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  Plant, Workplace, JobPosition, RiskFactorAssessment, RiskRating, RiskFactor,
} from "@/types/api";
import { RF_LABELS, RF_ORDER, RISK_RATINGS } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

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

const RATING_ORDER = ["1", "2", "2R", "3", "4"] as const;

function maxRating(ratings: (string | null | undefined)[]): RiskRating | null {
  let highest: RiskRating | null = null;
  let highestIdx = -1;
  for (const r of ratings) {
    if (!r) continue;
    const idx = RATING_ORDER.indexOf(r as RiskRating);
    if (idx > highestIdx) {
      highest = r as RiskRating;
      highestIdx = idx;
    }
  }
  return highest;
}

// ── RFA matrix per pozice ────────────────────────────────────────────────────

function PositionRfaMatrix({
  position,
  onRatingChange,
}: {
  position: JobPosition;
  onRatingChange: (rfa: RiskFactorAssessment | null) => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: rfa, isLoading } = useQuery<RiskFactorAssessment | null>({
    queryKey: ["rfa", position.id],
    queryFn: async () => {
      try {
        return await api.get<RiskFactorAssessment>(
          `/job-positions/${position.id}/risk-assessment`,
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });

  const setRatingMutation = useMutation({
    mutationFn: async ({ factor, rating }: { factor: RiskFactor; rating: RiskRating | null }) => {
      if (rfa) {
        return await api.patch<RiskFactorAssessment>(`/risk-factors/${rfa.id}`, {
          [factor]: rating,
        });
      }
      // Vytvořit nové RFA s tímto faktorem
      return await api.post<RiskFactorAssessment>("/risk-factors", {
        job_position_id: position.id,
        profese:         position.name,
        worker_count:    0,
        women_count:     0,
        [factor]:        rating,
      });
    },
    onSuccess: (data) => {
      qc.setQueryData(["rfa", position.id], data);
      qc.invalidateQueries({ queryKey: ["rfa-summary"] });
      onRatingChange(data);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function handleClick(factor: RiskFactor, rating: RiskRating) {
    const current = rfa?.[factor] ?? null;
    // Toggle — pokud už je toto rating vybráno, smazat (=null)
    const newValue = current === rating ? null : rating;
    setRatingMutation.mutate({ factor, rating: newValue });
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-400 py-3">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Načítám hodnocení rizik…
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-1.5 text-xs text-red-700">
          {error}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-100">
              <th className="text-left py-1.5 px-2 font-semibold text-gray-700 sticky left-0 bg-gray-100 min-w-[140px]">
                Rizikový faktor
              </th>
              {RISK_RATINGS.map(r => (
                <th key={r} className="py-1.5 px-2 font-semibold text-center w-12">
                  <span className={cn(
                    "inline-flex items-center justify-center rounded px-1.5 py-0.5 border",
                    CATEGORY_COLORS[r],
                  )}>
                    {r}
                  </span>
                </th>
              ))}
              <th className="py-1.5 px-2 font-semibold text-gray-500 w-14">N/A</th>
            </tr>
          </thead>
          <tbody>
            {RF_ORDER.map((factor, idx) => {
              const current = rfa?.[factor] ?? null;
              return (
                <tr key={factor} className={cn(idx % 2 === 0 ? "bg-white" : "bg-gray-50/50")}>
                  <td className="py-1.5 px-2 text-gray-700 sticky left-0 bg-inherit">
                    {RF_LABELS[factor]}
                  </td>
                  {RISK_RATINGS.map(r => {
                    const selected = current === r;
                    return (
                      <td key={r} className="text-center p-0.5">
                        <button
                          type="button"
                          onClick={() => handleClick(factor, r)}
                          disabled={setRatingMutation.isPending}
                          className={cn(
                            "w-9 h-7 rounded border text-xs font-semibold transition-all",
                            selected
                              ? `${CATEGORY_COLORS[r]} ring-2 ring-blue-500 ring-offset-1`
                              : "bg-white border-gray-200 text-gray-300 hover:border-gray-400 hover:text-gray-600",
                          )}
                          aria-pressed={selected}
                          aria-label={`${RF_LABELS[factor]}: kategorie ${r}`}
                        >
                          {selected ? r : "·"}
                        </button>
                      </td>
                    );
                  })}
                  <td className="text-center p-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        if (current !== null) {
                          setRatingMutation.mutate({ factor, rating: null });
                        }
                      }}
                      disabled={setRatingMutation.isPending || current === null}
                      className={cn(
                        "w-12 h-7 rounded border text-[10px] transition-all",
                        current === null
                          ? "bg-gray-100 border-gray-300 text-gray-500"
                          : "bg-white border-gray-200 text-gray-400 hover:border-red-400 hover:text-red-600",
                      )}
                      aria-label={`${RF_LABELS[factor]}: nehodnoceno`}
                    >
                      —
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-gray-400 italic">
        Tip: opětovným kliknutím na již vybranou kategorii ji zrušíte.
        Sloupec &bdquo;N/A&ldquo; označuje, že faktor se na pozici nevyskytuje.
      </p>
    </div>
  );
}

// ── Position card ────────────────────────────────────────────────────────────

function PositionCard({
  position,
  onCategoryChange,
}: {
  position: JobPosition;
  onCategoryChange: (positionId: string, category: RiskRating | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Lokální cache pro derived category — aktualizujeme když přijde RFA mutation
  const [localCategory, setLocalCategory] = useState<RiskRating | null>(
    (position.effective_category as RiskRating | null) ?? null,
  );

  function handleRfaChange(rfa: RiskFactorAssessment | null) {
    if (rfa) {
      const allFactors = RF_ORDER.map(f => rfa[f]);
      const max = maxRating(allFactors);
      setLocalCategory(max);
      onCategoryChange(position.id, max);
    }
  }

  const cat = localCategory;

  return (
    <div className="rounded-md border border-gray-200 bg-white">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-50 text-left"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-gray-400" /> : <ChevronRight className="h-3.5 w-3.5 text-gray-400" />}
        <span className="text-sm font-medium text-gray-900 flex-1 truncate">{position.name}</span>
        {cat ? (
          <Tooltip label={CATEGORY_DESCRIPTIONS[cat]}>
            <span className={cn(
              "shrink-0 inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[11px] font-bold border",
              CATEGORY_COLORS[cat],
            )}>
              kat. {cat}
            </span>
          </Tooltip>
        ) : (
          <Tooltip label="Žádný rizikový faktor není ohodnocen">
            <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-gray-100 text-gray-500 px-2 py-0.5 text-[11px] font-medium border border-gray-300">
              <AlertTriangle className="h-2.5 w-2.5" /> bez kat.
            </span>
          </Tooltip>
        )}
      </button>
      {expanded && (
        <div className="border-t border-gray-100 p-3">
          <PositionRfaMatrix position={position} onRatingChange={handleRfaChange} />
        </div>
      )}
    </div>
  );
}

// ── Workplace card ───────────────────────────────────────────────────────────

function WorkplaceCard({
  workplace,
  positions,
  positionCategories,
  onCategoryChange,
}: {
  workplace: Workplace;
  positions: JobPosition[];
  positionCategories: Record<string, RiskRating | null>;
  onCategoryChange: (positionId: string, category: RiskRating | null) => void;
}) {
  const allCats = positions.map(p =>
    positionCategories[p.id] ?? (p.effective_category as RiskRating | null) ?? null,
  );
  const maxCat = maxRating(allCats);

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
          <Tooltip label={`Maximum napříč pozicemi: ${CATEGORY_DESCRIPTIONS[maxCat]}`}>
            <span className={cn(
              "shrink-0 inline-flex items-center justify-center rounded-full px-2.5 py-1 text-xs font-bold border",
              CATEGORY_COLORS[maxCat],
            )}>
              kat. {maxCat}
            </span>
          </Tooltip>
        ) : (
          <Tooltip label="Žádná pozice nemá ohodnocené rizikové faktory">
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
        <div className="space-y-1.5">
          {positions.map(p => (
            <PositionCard
              key={p.id}
              position={p}
              onCategoryChange={onCategoryChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────────

export default function RiskOverviewPage() {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Lokální cache pro úpravy kategorií (pro live agregaci bez refetch)
  const [positionCategories, setPositionCategories] = useState<Record<string, RiskRating | null>>({});

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

  function handleCategoryChange(positionId: string, category: RiskRating | null) {
    setPositionCategories(prev => ({ ...prev, [positionId]: category }));
  }

  function getEffectiveCategory(p: JobPosition): RiskRating | null {
    return positionCategories[p.id] ?? (p.effective_category as RiskRating | null) ?? null;
  }

  // Souhrn
  const summaryCounts = workplaces.reduce(
    (acc, w) => {
      const cats = positionsFor(w.id).map(getEffectiveCategory);
      const cat = maxRating(cats);
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
              <Button size="sm" variant="outline">
                <ExternalLink className="h-4 w-4 mr-1.5" />
                Plný RFA editor (PDF, poznámky)
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
              <p className="text-xs text-gray-500 uppercase tracking-wide">Bez ohodnocení</p>
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
              // Plant-level agregace = max všech pracovišť
              const plantCats = wps.flatMap(w =>
                positionsFor(w.id).map(getEffectiveCategory),
              );
              const plantMax = maxRating(plantCats);

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
                      <div className="flex items-center gap-2">
                        {plantMax && (
                          <span className={cn(
                            "inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[11px] font-bold border",
                            CATEGORY_COLORS[plantMax],
                          )}>
                            kat. {plantMax}
                          </span>
                        )}
                        <span className="text-xs text-gray-400">
                          {wps.length} {wps.length === 1 ? "pracoviště" : "pracovišť"}
                        </span>
                      </div>
                    </button>

                    {isOpen && (
                      <div className="border-t border-gray-100 p-4 bg-gray-50/50">
                        {wps.length === 0 ? (
                          <p className="text-xs text-gray-400 italic">Žádná pracoviště</p>
                        ) : (
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                            {wps.map(w => (
                              <WorkplaceCard
                                key={w.id}
                                workplace={w}
                                positions={positionsFor(w.id)}
                                positionCategories={positionCategories}
                                onCategoryChange={handleCategoryChange}
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
          Klikněte na pozici pro rozbalení matrixu 13 rizikových faktorů.
          U každého faktoru přiřaďte kategorii kliknutím na 1/2/2R/3/4 (toggle).
          Úroveň rizika pracoviště = nejvyšší kategorie ze všech pozic na pracovišti.
          Pro upload PDF protokolů a další detaily použijte modul Provozovny.
        </div>
      </div>
    </div>
  );
}
