"use client";

/**
 * Modul Hodnocení rizik (ČSN ISO 45001 + Zákoník práce §102).
 *
 * Layout:
 *  - Header s tlačítkem „Přidat hodnocení"
 *  - Filter chips s počty (status, level)
 *  - Heatmap widget 5×5 s počtem rizik v každé buňce
 *  - Tabulka rizik (scope, hazard, P×Z badges, status, akce)
 *  - Detail modal (form + measures CRUD + revisions list)
 *
 * Liší se od /risk-overview (RFA aggregát pro úřady) — tady je strukturované
 * hodnocení konkrétních nebezpečných situací s opatřeními.
 */

import { Fragment, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Plus, Pencil, Archive, Eye, ShieldAlert, ListChecks,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  RiskAssessment, RiskMeasure, RiskScopeType, RiskStatus, RiskLevel,
  HazardCategory, ControlType, JobPosition, Plant, Workplace, OoppItem,
} from "@/types/api";
import {
  HAZARD_CATEGORY_LABELS, CONTROL_TYPE_LABELS, RISK_LEVEL_COLORS,
  RISK_LEVEL_LABELS, RISK_STATUS_LABELS, MEASURE_STATUS_LABELS,
} from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { SortableHeader } from "@/components/ui/sortable-header";
import { useTableSort } from "@/lib/use-table-sort";
import { cn } from "@/lib/utils";

const SELECT_CLS = "w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function levelFromScore(score: number | null): RiskLevel | null {
  if (score == null) return null;
  if (score <= 4) return "low";
  if (score <= 9) return "medium";
  if (score <= 15) return "high";
  return "critical";
}

function formatDate(d: string | null): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("cs-CZ");
  } catch {
    return d;
  }
}

// ── Heatmap widget ──────────────────────────────────────────────────────────

function RiskHeatmap({
  risks,
  onCellClick,
}: {
  risks: RiskAssessment[];
  onCellClick?: (p: number, s: number) => void;
}) {
  // 5×5 grid: counts[severity][probability]
  const counts = useMemo(() => {
    const grid: number[][] = Array.from({ length: 5 }, () => Array(5).fill(0));
    for (const r of risks) {
      const p = (r.residual_probability ?? r.initial_probability) - 1;
      const s = (r.residual_severity ?? r.initial_severity) - 1;
      if (p >= 0 && p < 5 && s >= 0 && s < 5) grid[s][p] += 1;
    }
    return grid;
  }, [risks]);

  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-xs font-semibold mb-2 flex items-center gap-1.5">
          <ShieldAlert className="h-3.5 w-3.5 text-orange-500" />
          Heatmap P × Z
        </div>
        <div className="text-[10px] text-gray-400 mb-1 text-center">
          Pravděpodobnost →
        </div>
        <div className="flex gap-2">
          <div className="flex flex-col-reverse justify-around text-[10px] text-gray-400 -rotate-180" style={{ writingMode: "vertical-rl" }}>
            <span>Závažnost</span>
          </div>
          <div className="flex-1">
            <table className="w-full text-xs">
              <tbody>
                {/* Reverse rows — severity 5 nahoře */}
                {[4, 3, 2, 1, 0].map((s) => (
                  <tr key={s}>
                    <td className="px-1 text-gray-400 text-right w-4">{s + 1}</td>
                    {[0, 1, 2, 3, 4].map((p) => {
                      const score = (s + 1) * (p + 1);
                      const level = levelFromScore(score);
                      const count = counts[s][p];
                      return (
                        <td key={p} className="p-0.5">
                          <button
                            type="button"
                            onClick={() => onCellClick?.(p + 1, s + 1)}
                            className={cn(
                              "w-full aspect-square rounded text-center transition-colors hover:opacity-80 cursor-pointer",
                              level === "low" && "bg-green-200 dark:bg-green-900/40",
                              level === "medium" && "bg-yellow-200 dark:bg-yellow-900/40",
                              level === "high" && "bg-orange-300 dark:bg-orange-900/50",
                              level === "critical" && "bg-red-400 dark:bg-red-900/60",
                            )}
                            title={`P=${p + 1}, Z=${s + 1}, score=${score} (${level})`}
                          >
                            <span className="text-[10px] font-mono text-gray-700 dark:text-gray-200">
                              {score}
                            </span>
                            {count > 0 && (
                              <div className="text-[10px] font-bold">{count}</div>
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr>
                  <td></td>
                  {[1, 2, 3, 4, 5].map((p) => (
                    <td key={p} className="text-[10px] text-gray-400 text-center">{p}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Hlavní stránka ──────────────────────────────────────────────────────────

export default function RisksPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editRisk, setEditRisk] = useState<RiskAssessment | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: risksRaw = [], isLoading } = useQuery<RiskAssessment[]>({
    queryKey: ["risk-assessments", statusFilter, levelFilter],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (statusFilter) qs.set("ra_status", statusFilter);
      if (levelFilter) qs.set("level", levelFilter);
      return api.get(`/risk-assessments${qs.toString() ? `?${qs.toString()}` : ""}`);
    },
  });
  const { data: risksAll = [] } = useQuery<RiskAssessment[]>({
    queryKey: ["risk-assessments", "all"],
    queryFn: () => api.get("/risk-assessments"),
    staleTime: 60_000,
  });

  const { sortedItems: risks, sortKey, sortDir, toggleSort } =
    useTableSort<RiskAssessment>(risksRaw, "created_at", "desc");

  // Counts per status / level
  const statusCounts = useMemo(() => ({
    all: risksAll.length,
    draft: risksAll.filter((r) => r.status === "draft").length,
    open: risksAll.filter((r) => r.status === "open").length,
    in_progress: risksAll.filter((r) => r.status === "in_progress").length,
    mitigated: risksAll.filter((r) => r.status === "mitigated").length,
    accepted: risksAll.filter((r) => r.status === "accepted").length,
    archived: risksAll.filter((r) => r.status === "archived").length,
  }), [risksAll]);

  const levelCounts = useMemo(() => ({
    all: risksAll.length,
    low:      risksAll.filter((r) => (r.residual_level ?? r.initial_level) === "low").length,
    medium:   risksAll.filter((r) => (r.residual_level ?? r.initial_level) === "medium").length,
    high:     risksAll.filter((r) => (r.residual_level ?? r.initial_level) === "high").length,
    critical: risksAll.filter((r) => (r.residual_level ?? r.initial_level) === "critical").length,
  }), [risksAll]);

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/risk-assessments/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-assessments"] }),
  });

  return (
    <div>
      <Header
        title="Hodnocení rizik"
        actions={
          <Button size="sm" onClick={() => { setServerError(null); setCreateOpen(true); }}>
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat hodnocení
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 mr-1 w-12">Stav:</span>
            {([
              { val: "",            label: "Všechny",      count: statusCounts.all },
              { val: "draft",       label: RISK_STATUS_LABELS.draft,       count: statusCounts.draft },
              { val: "open",        label: RISK_STATUS_LABELS.open,        count: statusCounts.open },
              { val: "in_progress", label: RISK_STATUS_LABELS.in_progress, count: statusCounts.in_progress },
              { val: "mitigated",   label: RISK_STATUS_LABELS.mitigated,   count: statusCounts.mitigated },
              { val: "accepted",    label: RISK_STATUS_LABELS.accepted,    count: statusCounts.accepted },
            ] as const).map(({ val, label, count }) => (
              <button
                key={val}
                onClick={() => setStatusFilter(val)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  statusFilter === val
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200",
                )}
              >
                {label} ({count})
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 mr-1 w-12">Úroveň:</span>
            {([
              { val: "",         label: "Vše",                          count: levelCounts.all },
              { val: "low",      label: RISK_LEVEL_LABELS.low,          count: levelCounts.low },
              { val: "medium",   label: RISK_LEVEL_LABELS.medium,       count: levelCounts.medium },
              { val: "high",     label: RISK_LEVEL_LABELS.high,         count: levelCounts.high },
              { val: "critical", label: RISK_LEVEL_LABELS.critical,     count: levelCounts.critical },
            ] as const).map(({ val, label, count }) => (
              <button
                key={val}
                onClick={() => setLevelFilter(val)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  levelFilter === val
                    ? "bg-orange-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200",
                )}
              >
                {label} ({count})
              </button>
            ))}
            <span className="ml-auto text-xs text-gray-400">{risks.length} zobrazeno</span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
          {/* Tabulka */}
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="space-y-0">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="h-12 animate-pulse bg-gray-50 mx-4 my-2 rounded" />
                  ))}
                </div>
              ) : risks.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                  <AlertTriangle className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">Žádná hodnocení rizik</p>
                  <p className="text-xs mt-1">Přidej první hodnocení tlačítkem výše</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100 bg-gray-50">
                        <th className="py-3 px-4 text-left text-xs font-medium text-gray-600">Scope</th>
                        <SortableHeader sortKey="hazard_category" current={sortKey} dir={sortDir} onSort={toggleSort}>Kategorie</SortableHeader>
                        <th className="py-3 px-4 text-left text-xs font-medium text-gray-600">Nebezpečí</th>
                        <SortableHeader sortKey="initial_score" current={sortKey} dir={sortDir} onSort={toggleSort}>P×Z init</SortableHeader>
                        <SortableHeader sortKey="residual_score" current={sortKey} dir={sortDir} onSort={toggleSort}>P×Z residual</SortableHeader>
                        <SortableHeader sortKey="status" current={sortKey} dir={sortDir} onSort={toggleSort}>Stav</SortableHeader>
                        <SortableHeader sortKey="review_due_date" current={sortKey} dir={sortDir} onSort={toggleSort}>Revize do</SortableHeader>
                        <th className="py-3 px-4 text-right text-xs font-medium text-gray-600">Akce</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {risks.map((r) => {
                        const scopeLabel =
                          r.scope_type === "workplace" ? r.workplace_name :
                          r.scope_type === "position" ? r.job_position_name :
                          r.scope_type === "plant" ? r.plant_name :
                          r.activity_description;
                        const initLevel = r.initial_level;
                        const resLevel = r.residual_level ?? r.initial_level;
                        return (
                          <tr key={r.id} className="hover:bg-gray-50">
                            <td className="py-3 px-4">
                              <div className="text-xs text-gray-500 uppercase">{r.scope_type}</div>
                              <div className="text-sm font-medium text-gray-900">{scopeLabel || "—"}</div>
                            </td>
                            <td className="py-3 px-4 text-xs text-gray-600">
                              {HAZARD_CATEGORY_LABELS[r.hazard_category] ?? r.hazard_category}
                            </td>
                            <td className="py-3 px-4 max-w-[280px]">
                              <div className="text-sm text-gray-800 truncate" title={r.hazard_description}>
                                {r.hazard_description}
                              </div>
                            </td>
                            <td className="py-3 px-4">
                              <span className={cn(
                                "rounded px-2 py-0.5 text-xs font-mono font-medium",
                                initLevel ? RISK_LEVEL_COLORS[initLevel] : "bg-gray-100 text-gray-500",
                              )}>
                                {r.initial_probability}×{r.initial_severity}={r.initial_score}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              {r.residual_probability != null && r.residual_severity != null ? (
                                <span className={cn(
                                  "rounded px-2 py-0.5 text-xs font-mono font-medium",
                                  resLevel ? RISK_LEVEL_COLORS[resLevel] : "bg-gray-100 text-gray-500",
                                )}>
                                  {r.residual_probability}×{r.residual_severity}={r.residual_score}
                                </span>
                              ) : (
                                <span className="text-xs text-gray-400">—</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-xs text-gray-600">
                              {RISK_STATUS_LABELS[r.status]}
                            </td>
                            <td className="py-3 px-4 text-xs text-gray-600">
                              {formatDate(r.review_due_date)}
                            </td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-1">
                                {r.measures_count > 0 && (
                                  <Tooltip label={`${r.measures_count} opatření, ${r.measures_open_count} otevřeno`}>
                                    <span className="inline-flex items-center gap-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                                      <ListChecks className="h-3 w-3" />
                                      {r.measures_open_count}/{r.measures_count}
                                    </span>
                                  </Tooltip>
                                )}
                                <button
                                  onClick={() => setEditRisk(r)}
                                  className="rounded p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                  title="Detail"
                                >
                                  <Eye className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={() => setEditRisk(r)}
                                  className="rounded p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                  title="Upravit"
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                {r.status !== "archived" && (
                                  <button
                                    onClick={() => {
                                      if (confirm(`Archivovat „${r.hazard_description.slice(0, 60)}"?`)) {
                                        archiveMutation.mutate(r.id);
                                      }
                                    }}
                                    className="rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                    title="Archivovat"
                                  >
                                    <Archive className="h-4 w-4" />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Heatmap */}
          <RiskHeatmap risks={risks} />
        </div>
      </div>

      {/* Create dialog */}
      <Dialog
        open={createOpen}
        onClose={() => { setCreateOpen(false); setServerError(null); }}
        title="Nové hodnocení rizika"
        size="lg"
      >
        <RiskAssessmentForm
          onSubmit={async (data) => {
            setServerError(null);
            try {
              await api.post("/risk-assessments", data);
              qc.invalidateQueries({ queryKey: ["risk-assessments"] });
              setCreateOpen(false);
            } catch (e) {
              setServerError(e instanceof ApiError ? e.detail : "Chyba serveru");
            }
          }}
          serverError={serverError}
        />
      </Dialog>

      {/* Detail / edit dialog */}
      <Dialog
        open={!!editRisk}
        onClose={() => { setEditRisk(null); setServerError(null); }}
        title={editRisk ? `Detail rizika: ${editRisk.hazard_description.slice(0, 60)}` : ""}
        size="lg"
      >
        {editRisk && (
          <RiskDetailBody
            risk={editRisk}
            onUpdated={() => qc.invalidateQueries({ queryKey: ["risk-assessments"] })}
            onClose={() => setEditRisk(null)}
          />
        )}
      </Dialog>
    </div>
  );
}

// ── Form pro nové hodnocení (kompaktní, ne wizard) ─────────────────────────

interface FormState {
  scope_type: RiskScopeType;
  workplace_id: string;
  job_position_id: string;
  plant_id: string;
  activity_description: string;
  hazard_category: HazardCategory;
  hazard_description: string;
  consequence_description: string;
  initial_probability: number;
  initial_severity: number;
  existing_controls: string;
  status: RiskStatus;
  review_due_date: string;
  notes: string;
}

function RiskAssessmentForm({
  onSubmit,
  serverError,
  defaults,
}: {
  onSubmit: (d: Partial<FormState>) => void | Promise<void>;
  serverError: string | null;
  defaults?: Partial<FormState>;
}) {
  const [state, setState] = useState<FormState>({
    scope_type: defaults?.scope_type ?? "workplace",
    workplace_id: defaults?.workplace_id ?? "",
    job_position_id: defaults?.job_position_id ?? "",
    plant_id: defaults?.plant_id ?? "",
    activity_description: defaults?.activity_description ?? "",
    hazard_category: defaults?.hazard_category ?? "slip_trip",
    hazard_description: defaults?.hazard_description ?? "",
    consequence_description: defaults?.consequence_description ?? "",
    initial_probability: defaults?.initial_probability ?? 3,
    initial_severity: defaults?.initial_severity ?? 3,
    existing_controls: defaults?.existing_controls ?? "",
    status: defaults?.status ?? "draft",
    review_due_date: defaults?.review_due_date ?? "",
    notes: defaults?.notes ?? "",
  });

  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces", "active"],
    queryFn: () => api.get("/workplaces?wp_status=active"),
  });
  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions"],
    queryFn: () => api.get("/job-positions"),
  });
  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants"),
  });

  const score = state.initial_probability * state.initial_severity;
  const level = levelFromScore(score);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const payload: Record<string, unknown> = {
          scope_type: state.scope_type,
          hazard_category: state.hazard_category,
          hazard_description: state.hazard_description,
          consequence_description: state.consequence_description,
          initial_probability: state.initial_probability,
          initial_severity: state.initial_severity,
          existing_controls: state.existing_controls || null,
          status: state.status,
          review_due_date: state.review_due_date || null,
          notes: state.notes || null,
        };
        if (state.scope_type === "workplace") payload.workplace_id = state.workplace_id || null;
        if (state.scope_type === "position") payload.job_position_id = state.job_position_id || null;
        if (state.scope_type === "plant") payload.plant_id = state.plant_id || null;
        if (state.scope_type === "activity") payload.activity_description = state.activity_description;
        return onSubmit(payload as Partial<FormState>);
      }}
      className="space-y-4"
    >
      {/* Scope */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Scope (čeho se týká) *</Label>
          <select
            value={state.scope_type}
            onChange={(e) => setState({ ...state, scope_type: e.target.value as RiskScopeType })}
            className={SELECT_CLS}
          >
            <option value="workplace">Pracoviště</option>
            <option value="position">Pracovní pozice</option>
            <option value="plant">Provozovna</option>
            <option value="activity">Činnost (free text)</option>
          </select>
        </div>
        <div>
          <Label>Kategorie nebezpečí *</Label>
          <select
            value={state.hazard_category}
            onChange={(e) => setState({ ...state, hazard_category: e.target.value as HazardCategory })}
            className={SELECT_CLS}
          >
            {(Object.keys(HAZARD_CATEGORY_LABELS) as HazardCategory[]).map((k) => (
              <option key={k} value={k}>{HAZARD_CATEGORY_LABELS[k]}</option>
            ))}
          </select>
        </div>
      </div>

      {state.scope_type === "workplace" && (
        <div>
          <Label>Pracoviště *</Label>
          <select
            value={state.workplace_id}
            onChange={(e) => setState({ ...state, workplace_id: e.target.value })}
            className={SELECT_CLS}
            required
          >
            <option value="">— vyber —</option>
            {workplaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </div>
      )}
      {state.scope_type === "position" && (
        <div>
          <Label>Pracovní pozice *</Label>
          <select
            value={state.job_position_id}
            onChange={(e) => setState({ ...state, job_position_id: e.target.value })}
            className={SELECT_CLS}
            required
          >
            <option value="">— vyber —</option>
            {positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      {state.scope_type === "plant" && (
        <div>
          <Label>Provozovna *</Label>
          <select
            value={state.plant_id}
            onChange={(e) => setState({ ...state, plant_id: e.target.value })}
            className={SELECT_CLS}
            required
          >
            <option value="">— vyber —</option>
            {plants.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      {state.scope_type === "activity" && (
        <div>
          <Label>Popis činnosti *</Label>
          <Input
            value={state.activity_description}
            onChange={(e) => setState({ ...state, activity_description: e.target.value })}
            required
            placeholder="např. Servisní výjezd k zákazníkovi"
          />
        </div>
      )}

      {/* Identifikace */}
      <div>
        <Label>Popis nebezpečí *</Label>
        <textarea
          value={state.hazard_description}
          onChange={(e) => setState({ ...state, hazard_description: e.target.value })}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
          placeholder="např. Pád z výšky při čištění oken nad 2m"
          required
        />
      </div>
      <div>
        <Label>Možný důsledek *</Label>
        <textarea
          value={state.consequence_description}
          onChange={(e) => setState({ ...state, consequence_description: e.target.value })}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
          placeholder="např. Zlomení končetin, smrt"
          required
        />
      </div>

      {/* P × Z */}
      <div className="grid grid-cols-3 gap-3 items-end">
        <div>
          <Label>Pravděpodobnost (1–5) *</Label>
          <select
            value={state.initial_probability}
            onChange={(e) => setState({ ...state, initial_probability: Number(e.target.value) })}
            className={SELECT_CLS}
          >
            {[1, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <div>
          <Label>Závažnost (1–5) *</Label>
          <select
            value={state.initial_severity}
            onChange={(e) => setState({ ...state, initial_severity: Number(e.target.value) })}
            className={SELECT_CLS}
          >
            {[1, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <div>
          <Label>Score (P×Z)</Label>
          <div className={cn(
            "rounded-md px-3 py-2 text-sm font-mono font-bold text-center",
            level ? RISK_LEVEL_COLORS[level] : "bg-gray-100",
          )}>
            {score} {level && `— ${RISK_LEVEL_LABELS[level]}`}
          </div>
        </div>
      </div>

      {/* Stávající kontroly */}
      <div>
        <Label>Stávající opatření / OOPP</Label>
        <textarea
          value={state.existing_controls}
          onChange={(e) => setState({ ...state, existing_controls: e.target.value })}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
          placeholder="Popis toho, co je už zavedeno (kryty, postupy, OOPP...)"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Stav</Label>
          <select
            value={state.status}
            onChange={(e) => setState({ ...state, status: e.target.value as RiskStatus })}
            className={SELECT_CLS}
          >
            <option value="draft">{RISK_STATUS_LABELS.draft}</option>
            <option value="open">{RISK_STATUS_LABELS.open}</option>
            <option value="in_progress">{RISK_STATUS_LABELS.in_progress}</option>
            <option value="mitigated">{RISK_STATUS_LABELS.mitigated}</option>
            <option value="accepted">{RISK_STATUS_LABELS.accepted}</option>
          </select>
        </div>
        <div>
          <Label>Příští revize</Label>
          <Input
            type="date"
            value={state.review_due_date}
            onChange={(e) => setState({ ...state, review_due_date: e.target.value })}
          />
        </div>
      </div>

      <div>
        <Label>Poznámky</Label>
        <textarea
          value={state.notes}
          onChange={(e) => setState({ ...state, notes: e.target.value })}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
        />
      </div>

      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {String(serverError)}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
        <Button type="submit">Uložit</Button>
      </div>
    </form>
  );
}

// ── Detail body s opatřeními ───────────────────────────────────────────────

function RiskDetailBody({
  risk,
  onUpdated,
  onClose,
}: {
  risk: RiskAssessment;
  onUpdated: () => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"detail" | "measures">("detail");
  const [serverError, setServerError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: (data: Partial<FormState>) =>
      api.patch(`/risk-assessments/${risk.id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["risk-assessments"] });
      onUpdated();
    },
    onError: (e) => setServerError(e instanceof ApiError ? e.detail : "Chyba"),
  });

  return (
    <div>
      <div className="flex gap-2 border-b border-gray-100 mb-4">
        {(["detail", "measures"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t ? "border-blue-600 text-blue-700" : "border-transparent text-gray-500",
            )}
          >
            {t === "detail" ? "Detail" : `Opatření (${risk.measures_count})`}
          </button>
        ))}
      </div>

      {tab === "detail" && (
        <RiskAssessmentForm
          defaults={{
            scope_type: risk.scope_type,
            workplace_id: risk.workplace_id ?? "",
            job_position_id: risk.job_position_id ?? "",
            plant_id: risk.plant_id ?? "",
            activity_description: risk.activity_description ?? "",
            hazard_category: risk.hazard_category,
            hazard_description: risk.hazard_description,
            consequence_description: risk.consequence_description,
            initial_probability: risk.initial_probability,
            initial_severity: risk.initial_severity,
            existing_controls: risk.existing_controls ?? "",
            status: risk.status,
            review_due_date: risk.review_due_date ?? "",
            notes: risk.notes ?? "",
          }}
          onSubmit={(data) => updateMutation.mutate(data)}
          serverError={serverError}
        />
      )}

      {tab === "measures" && <MeasuresPanel risk={risk} onClose={onClose} />}
    </div>
  );
}

// ── Měření / opatření panel ────────────────────────────────────────────────

function MeasuresPanel({ risk, onClose }: { risk: RiskAssessment; onClose: () => void }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: measures = [] } = useQuery<RiskMeasure[]>({
    queryKey: ["risk-measures", risk.id],
    queryFn: () => api.get(`/risk-assessments/${risk.id}/measures`),
  });

  const { data: ooppItems = [] } = useQuery<OoppItem[]>({
    queryKey: ["oopp-items", "by-position", risk.job_position_id],
    queryFn: () =>
      risk.job_position_id
        ? api.get(`/oopp/items?job_position_id=${risk.job_position_id}&item_status=active`)
        : Promise.resolve([]),
    enabled: !!risk.job_position_id,
  });

  const createMutation = useMutation({
    mutationFn: (data: Partial<RiskMeasure>) =>
      api.post(`/risk-assessments/${risk.id}/measures`, {
        ...data,
        risk_assessment_id: risk.id,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["risk-measures", risk.id] });
      qc.invalidateQueries({ queryKey: ["risk-assessments"] });
      setAdding(false);
    },
    onError: (e) => setServerError(e instanceof ApiError ? e.detail : "Chyba"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<RiskMeasure> }) =>
      api.patch(`/risk-measures/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["risk-measures", risk.id] });
      qc.invalidateQueries({ queryKey: ["risk-assessments"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/risk-measures/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-measures", risk.id] }),
  });

  return (
    <div className="space-y-4">
      <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 px-3 py-2 text-xs text-blue-800 dark:text-blue-200">
        Hierarchie kontrol (ISO 45001) — preferuj vyšší úrovně:
        <strong> Eliminace → Substituce → Inženýrské → Administrativní → OOPP</strong>.
        OOPP je až poslední cesta.
      </div>

      {/* Existing measures */}
      <div className="space-y-2">
        {measures.length === 0 ? (
          <div className="text-sm text-gray-400 py-4 text-center">Žádná opatření</div>
        ) : (
          measures.map((m) => (
            <Fragment key={m.id}>
              <div className="rounded-md border border-gray-200 p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-700">
                        {CONTROL_TYPE_LABELS[m.control_type]}
                      </span>
                      <span className={cn(
                        "rounded px-1.5 py-0.5 text-xs font-medium",
                        m.status === "done" && "bg-green-100 text-green-700",
                        m.status === "in_progress" && "bg-yellow-100 text-yellow-700",
                        m.status === "planned" && "bg-gray-100 text-gray-700",
                        m.status === "cancelled" && "bg-gray-100 text-gray-400 line-through",
                      )}>
                        {MEASURE_STATUS_LABELS[m.status]}
                      </span>
                      {m.deadline && (
                        <span className="text-xs text-gray-500">do {formatDate(m.deadline)}</span>
                      )}
                    </div>
                    <div className="text-sm text-gray-800">{m.description}</div>
                    {m.position_oopp_item_name && (
                      <div className="text-xs text-blue-700 mt-1">
                        🛡 OOPP: {m.position_oopp_item_name}
                      </div>
                    )}
                    {m.responsible_employee_name && (
                      <div className="text-xs text-gray-500 mt-1">
                        Odpovědný: {m.responsible_employee_name}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <select
                      value={m.status}
                      onChange={(e) =>
                        updateMutation.mutate({
                          id: m.id,
                          data: { status: e.target.value as RiskMeasure["status"] },
                        })
                      }
                      className="text-xs rounded border border-gray-200 px-1 py-0.5"
                    >
                      {(Object.keys(MEASURE_STATUS_LABELS) as RiskMeasure["status"][]).map((s) => (
                        <option key={s} value={s}>{MEASURE_STATUS_LABELS[s]}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => {
                        if (confirm("Smazat opatření?")) deleteMutation.mutate(m.id);
                      }}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Smazat
                    </button>
                  </div>
                </div>
              </div>
            </Fragment>
          ))
        )}
      </div>

      {/* Add new measure */}
      {adding ? (
        <NewMeasureForm
          riskId={risk.id}
          ooppItems={ooppItems}
          onCancel={() => { setAdding(false); setServerError(null); }}
          onSubmit={(data) => createMutation.mutate(data)}
          serverError={serverError}
        />
      ) : (
        <Button variant="outline" onClick={() => setAdding(true)}>
          <Plus className="h-3.5 w-3.5 mr-1" />
          Přidat opatření
        </Button>
      )}

      <div className="flex justify-end pt-2 border-t border-gray-100">
        <Button variant="outline" onClick={onClose}>Zavřít</Button>
      </div>
    </div>
  );
}

function NewMeasureForm({
  riskId,
  ooppItems,
  onCancel,
  onSubmit,
  serverError,
}: {
  riskId: string;
  ooppItems: OoppItem[];
  onCancel: () => void;
  onSubmit: (d: Partial<RiskMeasure>) => void;
  serverError: string | null;
}) {
  const [controlType, setControlType] = useState<ControlType>("engineering");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [ooppItemId, setOoppItemId] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          risk_assessment_id: riskId,
          control_type: controlType,
          description,
          deadline: deadline || null,
          position_oopp_item_id: controlType === "ppe" && ooppItemId ? ooppItemId : null,
          status: "planned",
        });
      }}
      className="rounded-md border border-blue-200 bg-blue-50 dark:bg-blue-900/20 p-3 space-y-3"
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Typ opatření</Label>
          <select
            value={controlType}
            onChange={(e) => setControlType(e.target.value as ControlType)}
            className={SELECT_CLS}
          >
            <option value="elimination">{CONTROL_TYPE_LABELS.elimination}</option>
            <option value="substitution">{CONTROL_TYPE_LABELS.substitution}</option>
            <option value="engineering">{CONTROL_TYPE_LABELS.engineering}</option>
            <option value="administrative">{CONTROL_TYPE_LABELS.administrative}</option>
            <option value="ppe">{CONTROL_TYPE_LABELS.ppe}</option>
          </select>
        </div>
        <div>
          <Label className="text-xs">Termín</Label>
          <Input
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </div>
      </div>
      <div>
        <Label className="text-xs">Popis</Label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
          required
        />
      </div>
      {controlType === "ppe" && ooppItems.length > 0 && (
        <div>
          <Label className="text-xs">Položka OOPP (provázanost s OOPP modulem)</Label>
          <select
            value={ooppItemId}
            onChange={(e) => setOoppItemId(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">— bez vazby —</option>
            {ooppItems.map((it) => (
              <option key={it.id} value={it.id}>{it.name}</option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Při výběru OOPP se automaticky přidá do tabulky výdejů zaměstnanců na pozici.
          </p>
        </div>
      )}
      {serverError && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {String(serverError)}
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>Zrušit</Button>
        <Button type="submit">Přidat</Button>
      </div>
    </form>
  );
}
