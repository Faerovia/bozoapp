"use client";

/**
 * Modul OOPP (NV 390/2021 Sb. Příloha č. 2).
 *
 * 3 záložky:
 *  1) Vyhodnocení rizik — výběr pozice + matrix 14×26 (checkboxy)
 *  2) OOPP dle pozic     — pozice s vyplněným gridem, k nim přidělené OOPP
 *  3) Výdeje zaměstnancům — záznamy + zaznamenat nový výdej
 */

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Pencil, Trash2, ShieldAlert, Boxes, ClipboardList, Save, Download,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useTableSort } from "@/lib/use-table-sort";
import { SortableHeader } from "@/components/ui/sortable-header";
import type {
  Employee, JobPosition, OoppCatalog, OoppItem, OoppIssue, RiskGrid,
} from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const VALIDITY_LABELS: Record<string, string> = {
  no_expiry: "Bez expirace",
  valid: "Platné",
  expiring_soon: "Brzy expiruje",
  expired: "PROŠLO",
};
const VALIDITY_COLORS: Record<string, string> = {
  no_expiry: "bg-gray-100 text-gray-500",
  valid: "bg-green-100 text-green-700",
  expiring_soon: "bg-amber-100 text-amber-700",
  expired: "bg-red-100 text-red-700",
};

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("cs-CZ");
}

function errMsg(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Chyba serveru";
}

// ── Risk grid matrix ─────────────────────────────────────────────────────────

function RiskGridMatrix({
  positionId,
  catalog,
}: {
  positionId: string;
  catalog: OoppCatalog;
}) {
  const qc = useQueryClient();
  const [matrix, setMatrix] = useState<Record<string, Set<number>>>({});
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery<RiskGrid>({
    queryKey: ["oopp-grid", positionId],
    queryFn: async () => {
      try {
        return await api.get<RiskGrid>(`/job-positions/${positionId}/oopp-grid`);
      } catch (err) {
        // 404 = grid neexistuje, vrátíme prázdný
        if (err instanceof ApiError && err.status === 404) {
          return {
            id: "",
            tenant_id: "",
            job_position_id: positionId,
            grid: {},
            has_any_risk: false,
            created_by: "",
          };
        }
        throw err;
      }
    },
  });

  useEffect(() => {
    if (data) {
      const next: Record<string, Set<number>> = {};
      for (const [bp, cols] of Object.entries(data.grid)) {
        next[bp] = new Set(cols);
      }
      setMatrix(next);
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, number[]> = {};
      for (const [bp, set] of Object.entries(matrix)) {
        if (set.size > 0) payload[bp] = Array.from(set).sort((a, b) => a - b);
      }
      return api.put(`/job-positions/${positionId}/oopp-grid`, { grid: payload });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oopp-grid", positionId] });
      qc.invalidateQueries({ queryKey: ["oopp-positions"] });
      setError(null);
    },
    onError: (err) => setError(errMsg(err)),
  });

  function toggle(bp: string, col: number) {
    setMatrix((prev) => {
      const next = { ...prev };
      const set = new Set(prev[bp] ?? []);
      if (set.has(col)) set.delete(col);
      else set.add(col);
      next[bp] = set;
      return next;
    });
  }

  if (isLoading) {
    return <div className="h-32 animate-pulse bg-gray-50 rounded" />;
  }

  // Skupiny sloupců pro hlavičku
  const groups: { name: string; from: number; to: number }[] = [];
  let currentGroup = "";
  let groupStart = 1;
  catalog.risk_columns.forEach((rc, idx) => {
    if (rc.group !== currentGroup) {
      if (currentGroup) {
        groups.push({ name: currentGroup, from: groupStart, to: idx });
      }
      currentGroup = rc.group;
      groupStart = idx + 1;
    }
  });
  groups.push({ name: currentGroup, from: groupStart, to: catalog.risk_columns.length });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <ShieldAlert className="h-4 w-4 text-amber-500" />
        Zaškrtni rizika, kterým je pozice vystavena. Tabulka odpovídá Příloze č. 2 NV 390/2021 Sb.
      </div>

      <div className="overflow-auto border border-gray-200 rounded">
        <table className="text-xs">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              <th className="text-left p-2 sticky left-0 bg-gray-50 z-10 border-r border-gray-200" rowSpan={2}>
                Část těla
              </th>
              {groups.map((g) => (
                <th
                  key={g.name}
                  colSpan={g.to - g.from + 1}
                  className="text-center p-1 border-l border-gray-200 font-semibold uppercase"
                >
                  {g.name}
                </th>
              ))}
            </tr>
            <tr>
              {catalog.risk_columns.map((rc) => (
                <th
                  key={rc.col}
                  className="p-2 border-l border-gray-200 align-middle text-center"
                  style={{ width: 90, minWidth: 90, maxWidth: 90 }}
                  title={rc.label}
                >
                  <div className="text-xs leading-snug font-medium break-words whitespace-normal">
                    {rc.label}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {catalog.body_parts.map((bp, idx) => (
              <tr key={bp.key} className={idx % 2 === 0 ? "bg-white" : "bg-gray-50/40"}>
                <td className="p-2 sticky left-0 z-10 border-r border-gray-200 bg-inherit font-medium text-sm">
                  {bp.key}. {bp.label}
                </td>
                {catalog.risk_columns.map((rc) => {
                  const checked = matrix[bp.key]?.has(rc.col) ?? false;
                  return (
                    <td
                      key={rc.col}
                      className="text-center border-l border-gray-100 p-2"
                      style={{ width: 90, minWidth: 90 }}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(bp.key, rc.col)}
                        className="h-5 w-5 cursor-pointer"
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
          <Save className="h-4 w-4 mr-1.5" />
          Uložit hodnocení
        </Button>
      </div>
    </div>
  );
}

// ── Tab 1: Vyhodnocení rizik ─────────────────────────────────────────────────

function RiskGridTab({
  positions,
  catalog,
}: {
  positions: JobPosition[];
  catalog: OoppCatalog;
}) {
  const [selectedId, setSelectedId] = useState<string>("");

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="space-y-1.5">
          <Label htmlFor="grid_position">Pracovní pozice</Label>
          <select
            id="grid_position"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">— vyber pozici —</option>
            {positions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.workplace_name ? ` · ${p.workplace_name}` : ""}
                {p.plant_name ? ` · ${p.plant_name}` : ""}
              </option>
            ))}
          </select>
        </div>

        {selectedId ? (
          <RiskGridMatrix positionId={selectedId} catalog={catalog} />
        ) : (
          <div className="text-sm text-gray-400 text-center py-8">
            Vyber pozici pro zobrazení matice rizik.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Tab 2: OOPP dle pozic ────────────────────────────────────────────────────

function OoppItemForm({
  positionId,
  bodyPart,
  defaultValues,
  onSubmit,
  isSubmitting,
  error,
  bodyParts,
}: {
  positionId: string;
  bodyPart?: string;
  defaultValues?: Partial<OoppItem>;
  onSubmit: (data: { body_part: string; name: string; valid_months: number | null; notes: string | null }) => void;
  isSubmitting: boolean;
  error: string | null;
  bodyParts: { key: string; label: string }[];
}) {
  const [form, setForm] = useState({
    body_part: defaultValues?.body_part ?? bodyPart ?? "G",
    name: defaultValues?.name ?? "",
    valid_months: defaultValues?.valid_months?.toString() ?? "",
    notes: defaultValues?.notes ?? "",
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          body_part: form.body_part,
          name: form.name,
          valid_months: form.valid_months ? parseInt(form.valid_months, 10) : null,
          notes: form.notes || null,
        });
      }}
      className="space-y-3"
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="body_part">Část těla *</Label>
          <select
            id="body_part"
            value={form.body_part}
            onChange={(e) => setForm({ ...form, body_part: e.target.value })}
            className={SELECT_CLS}
          >
            {bodyParts.map((bp) => (
              <option key={bp.key} value={bp.key}>{bp.key}. {bp.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Perioda výdeje (měsíce)</Label>
          <Input
            id="valid_months"
            type="number"
            min="1"
            value={form.valid_months}
            onChange={(e) => setForm({ ...form, valid_months: e.target.value })}
            placeholder="např. 12"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="name">Název OOPP *</Label>
        <Input
          id="name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="např. Pracovní rukavice odolné proti řezu"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky</Label>
        <textarea
          id="notes"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          rows={2}
          className={cn(SELECT_CLS, "resize-none")}
        />
      </div>
      <input type="hidden" value={positionId} readOnly />
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

function PositionOoppDetail({
  position,
  catalog,
}: {
  position: { id: string; name: string };
  catalog: OoppCatalog;
}) {
  const qc = useQueryClient();
  const [addModal, setAddModal] = useState<{ bodyPart: string } | null>(null);
  const [editItem, setEditItem] = useState<OoppItem | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: items = [] } = useQuery<OoppItem[]>({
    queryKey: ["oopp-items", position.id],
    queryFn: () => api.get(`/oopp/items?job_position_id=${position.id}&item_status=active`),
  });

  const { data: grid } = useQuery<RiskGrid | null>({
    queryKey: ["oopp-grid", position.id],
    queryFn: async () => {
      try {
        return await api.get<RiskGrid>(`/job-positions/${position.id}/oopp-grid`);
      } catch {
        return null;
      }
    },
  });

  const checkedBodyParts = new Set(Object.keys(grid?.grid ?? {}));

  const createItem = useMutation({
    mutationFn: (payload: { body_part: string; name: string; valid_months: number | null; notes: string | null }) =>
      api.post("/oopp/items", { ...payload, job_position_id: position.id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oopp-items", position.id] });
      setAddModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });

  const updateItem = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<OoppItem> }) =>
      api.patch(`/oopp/items/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oopp-items", position.id] });
      setEditItem(null);
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });

  const archiveItem = useMutation({
    mutationFn: (id: string) => api.delete(`/oopp/items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oopp-items", position.id] }),
  });

  const itemsByBodyPart = items.reduce<Record<string, OoppItem[]>>((acc, item) => {
    (acc[item.body_part] ??= []).push(item);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      {catalog.body_parts.map((bp) => {
        const isChecked = checkedBodyParts.has(bp.key);
        const list = itemsByBodyPart[bp.key] ?? [];

        // Skryj body parts, pro které není nic zaškrtnuté A není přidáno OOPP
        if (!isChecked && list.length === 0) return null;

        return (
          <div key={bp.key} className="border border-gray-100 rounded-md p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-800">
                  {bp.key}. {bp.label}
                </span>
                {isChecked && (
                  <span className="rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 text-xs font-medium">
                    {grid?.grid[bp.key].length} riziko/a
                  </span>
                )}
              </div>
              <button
                onClick={() => { setFormError(null); setAddModal({ bodyPart: bp.key }); }}
                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                <Plus className="h-3 w-3" /> Přidat OOPP
              </button>
            </div>

            {list.length === 0 ? (
              <div className="text-xs text-gray-400 pl-2">Zatím žádné OOPP přiděleno.</div>
            ) : (
              <ul className="divide-y divide-gray-50">
                {list.map((item) => (
                  <li key={item.id} className="py-1.5 flex items-center justify-between">
                    <div>
                      <span className="font-medium text-gray-800">{item.name}</span>
                      {item.valid_months && (
                        <span className="ml-2 text-xs text-gray-500">
                          výdej á {item.valid_months} měs.
                        </span>
                      )}
                      {item.notes && (
                        <span className="ml-2 text-xs text-gray-400">· {item.notes}</span>
                      )}
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => { setFormError(null); setEditItem(item); }}
                        className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                        title="Upravit"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Archivovat ${item.name}?`)) archiveItem.mutate(item.id);
                        }}
                        className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                        title="Archivovat"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      {/* Dialog: přidat OOPP */}
      <Dialog
        open={!!addModal}
        onClose={() => { setAddModal(null); setFormError(null); }}
        title="Přidat OOPP"
        size="md"
      >
        {addModal && (
          <OoppItemForm
            positionId={position.id}
            bodyPart={addModal.bodyPart}
            bodyParts={catalog.body_parts}
            onSubmit={(data) => createItem.mutate(data)}
            isSubmitting={createItem.isPending}
            error={formError}
          />
        )}
      </Dialog>

      {/* Dialog: editace OOPP */}
      <Dialog
        open={!!editItem}
        onClose={() => { setEditItem(null); setFormError(null); }}
        title={editItem ? `Upravit: ${editItem.name}` : ""}
        size="md"
      >
        {editItem && (
          <OoppItemForm
            positionId={position.id}
            defaultValues={editItem}
            bodyParts={catalog.body_parts}
            onSubmit={(data) => updateItem.mutate({ id: editItem.id, data })}
            isSubmitting={updateItem.isPending}
            error={formError}
          />
        )}
      </Dialog>
    </div>
  );
}

function PositionsTab({ catalog }: { catalog: OoppCatalog }) {
  const { data: positions = [] } = useQuery<{ id: string; name: string; workplace_id: string }[]>({
    queryKey: ["oopp-positions"],
    queryFn: () => api.get("/oopp/positions"),
  });
  const [selectedId, setSelectedId] = useState<string>("");
  const selected = positions.find((p) => p.id === selectedId);

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        {positions.length === 0 ? (
          <div className="text-sm text-gray-400 text-center py-8">
            Zatím žádná pozice nemá vyplněnou matici rizik.
            Přepni se na záložku &bdquo;Vyhodnocení rizik&ldquo;.
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="positions">Pozice s vyhodnoceným rizikem</Label>
              <select
                id="positions"
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className={SELECT_CLS}
              >
                <option value="">— vyber pozici —</option>
                {positions.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            {selected && (
              <PositionOoppDetail
                position={{ id: selected.id, name: selected.name }}
                catalog={catalog}
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Tab 3: Issues (výdeje) ───────────────────────────────────────────────────

function IssuesTab() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: issuesRaw = [] } = useQuery<OoppIssue[]>({
    queryKey: ["oopp-issues"],
    queryFn: () => api.get("/oopp/issues?issue_status=active"),
  });
  const {
    sortedItems: issues,
    sortKey, sortDir, toggleSort,
  } = useTableSort<OoppIssue>(issuesRaw, "valid_until", "asc");

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees", "active"],
    queryFn: () => api.get("/employees?employee_status=active"),
  });

  const { data: items = [] } = useQuery<OoppItem[]>({
    queryKey: ["oopp-items", "all"],
    queryFn: () => api.get("/oopp/items?item_status=active"),
  });

  const [form, setForm] = useState({
    employee_id: "",
    position_oopp_item_id: "",
    issued_at: new Date().toISOString().slice(0, 10),
    quantity: "1",
    size_spec: "",
    notes: "",
  });

  const createIssue = useMutation({
    mutationFn: () =>
      api.post("/oopp/issues", {
        employee_id: form.employee_id,
        position_oopp_item_id: form.position_oopp_item_id,
        issued_at: form.issued_at,
        quantity: parseInt(form.quantity, 10) || 1,
        size_spec: form.size_spec || null,
        notes: form.notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oopp-issues"] });
      setCreateOpen(false);
      setForm({
        employee_id: "",
        position_oopp_item_id: "",
        issued_at: new Date().toISOString().slice(0, 10),
        quantity: "1",
        size_spec: "",
        notes: "",
      });
      setFormError(null);
    },
    onError: (err) => setFormError(errMsg(err)),
  });

  const archiveIssue = useMutation({
    mutationFn: (id: string) => api.delete(`/oopp/issues/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oopp-issues"] }),
  });

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <span className="text-sm text-gray-500">{issues.length} aktivních výdejů</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                const resp = await fetch("/api/v1/oopp/issues.pdf");
                if (!resp.ok) { alert("Stažení selhalo"); return; }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "oopp-vydeje.pdf";
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download className="h-4 w-4 mr-1.5" />
              PDF přehled
            </Button>
            <Button size="sm" onClick={() => { setFormError(null); setCreateOpen(true); }}>
              <Plus className="h-4 w-4 mr-1.5" />
              Zaznamenat výdej
            </Button>
          </div>
        </div>

        {issues.length === 0 ? (
          <div className="text-sm text-gray-400 text-center py-12">
            Zatím žádné výdeje OOPP.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <SortableHeader sortKey="employee_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Zaměstnanec</SortableHeader>
                  <SortableHeader sortKey="item_name" current={sortKey} dir={sortDir} onSort={toggleSort}>OOPP</SortableHeader>
                  <SortableHeader sortKey="issued_at" current={sortKey} dir={sortDir} onSort={toggleSort}>Posl. výdej</SortableHeader>
                  <SortableHeader sortKey="valid_until" current={sortKey} dir={sortDir} onSort={toggleSort}>Další výdej</SortableHeader>
                  <SortableHeader sortKey="validity_status" current={sortKey} dir={sortDir} onSort={toggleSort}>Stav</SortableHeader>
                  <th className="py-3 px-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {issues.map((issue) => (
                  <tr key={issue.id} className="hover:bg-gray-50/50">
                    <td className="py-2.5 px-4 font-medium text-gray-900">
                      {issue.employee_name || "—"}
                    </td>
                    <td className="py-2.5 px-4 text-gray-700">
                      {issue.item_name}
                      {issue.body_part && (
                        <span className="ml-1 text-xs text-gray-400">({issue.body_part})</span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-gray-600">{fmtDate(issue.issued_at)}</td>
                    <td className="py-2.5 px-4 text-gray-600">{fmtDate(issue.valid_until)}</td>
                    <td className="py-2.5 px-4">
                      <span className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        VALIDITY_COLORS[issue.validity_status] || "bg-gray-100"
                      )}>
                        {VALIDITY_LABELS[issue.validity_status] || issue.validity_status}
                      </span>
                    </td>
                    <td className="py-2.5 px-4">
                      <button
                        onClick={() => {
                          if (confirm("Vyřadit výdej?")) archiveIssue.mutate(issue.id);
                        }}
                        className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                        title="Vyřadit"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {/* Dialog: zaznamenat výdej */}
      <Dialog
        open={createOpen}
        onClose={() => { setCreateOpen(false); setFormError(null); }}
        title="Zaznamenat výdej OOPP"
        size="md"
      >
        <form
          onSubmit={(e) => { e.preventDefault(); createIssue.mutate(); }}
          className="space-y-3"
        >
          <div className="space-y-1.5">
            <Label htmlFor="i_emp">Zaměstnanec *</Label>
            <select
              id="i_emp"
              value={form.employee_id}
              onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
              className={SELECT_CLS}
              required
            >
              <option value="">— vyber —</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>{e.full_name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="i_item">OOPP položka *</Label>
            <select
              id="i_item"
              value={form.position_oopp_item_id}
              onChange={(e) => setForm({ ...form, position_oopp_item_id: e.target.value })}
              className={SELECT_CLS}
              required
            >
              <option value="">— vyber —</option>
              {items.map((it) => (
                <option key={it.id} value={it.id}>
                  {it.name} ({it.body_part}{it.valid_months ? `, á ${it.valid_months} m` : ""})
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5 col-span-2">
              <Label htmlFor="i_date">Datum výdeje *</Label>
              <Input
                id="i_date"
                type="date"
                value={form.issued_at}
                onChange={(e) => setForm({ ...form, issued_at: e.target.value })}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="i_qty">Počet ks</Label>
              <Input
                id="i_qty"
                type="number"
                min="1"
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="i_size">Velikost</Label>
            <Input
              id="i_size"
              value={form.size_spec}
              onChange={(e) => setForm({ ...form, size_spec: e.target.value })}
              placeholder="např. L, 42, vel. M"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="i_notes">Poznámka</Label>
            <textarea
              id="i_notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className={cn(SELECT_CLS, "resize-none")}
            />
          </div>

          {formError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {formError}
            </div>
          )}

          <div className="flex justify-end">
            <Button type="submit" loading={createIssue.isPending}>Uložit</Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────────

type Tab = "grid" | "positions" | "issues";

export default function OoppPage() {
  const [tab, setTab] = useState<Tab>("grid");

  const { data: catalog } = useQuery<OoppCatalog>({
    queryKey: ["oopp-catalog"],
    queryFn: () => api.get("/oopp/catalog"),
    staleTime: Infinity,
  });

  const { data: positions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions", "active"],
    queryFn: () => api.get("/job-positions?jp_status=active"),
  });

  return (
    <div>
      <Header title="OOPP" />

      <div className="px-6 pt-4">
        <div className="flex gap-1 border-b border-gray-200">
          {([
            { key: "grid",      label: "Vyhodnocení rizik",     icon: ShieldAlert },
            { key: "positions", label: "OOPP dle pozic",        icon: Boxes },
            { key: "issues",    label: "Výdeje zaměstnancům",   icon: ClipboardList },
          ] as { key: Tab; label: string; icon: typeof ShieldAlert }[]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
                tab === t.key
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              )}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-6">
        {!catalog ? (
          <div className="h-32 animate-pulse bg-gray-50 rounded" />
        ) : tab === "grid" ? (
          <RiskGridTab positions={positions} catalog={catalog} />
        ) : tab === "positions" ? (
          <PositionsTab catalog={catalog} />
        ) : (
          <IssuesTab />
        )}
      </div>
    </div>
  );
}
