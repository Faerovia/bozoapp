"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Pencil, Trash2, Download, FileText, Upload, Sparkles,
  Stethoscope, Activity,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useTableSort } from "@/lib/use-table-sort";
import { SortableHeader } from "@/components/ui/sortable-header";
import type { MedicalExam, Employee, SpecialtyCatalogEntry } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const PREVENTIVE_TYPES = [
  { value: "vstupni",     label: "Vstupní" },
  { value: "periodicka",  label: "Periodická" },
  { value: "vystupni",    label: "Výstupní" },
  { value: "mimoradna",   label: "Mimořádná" },
];

const EXAM_RESULTS = [
  { value: "zpusobily",            label: "Způsobilý" },
  { value: "zpusobily_omezeni",    label: "Způsobilý s omezením" },
  { value: "nezpusobily",          label: "Nezpůsobilý" },
  { value: "pozbyl_zpusobilosti",  label: "Pozbyl způsobilosti" },
];

const VALIDITY_STATUS_LABELS: Record<string, string> = {
  valid:          "Platné",
  expiring_soon:  "Expirují brzy",
  expired:        "Expirovaná",
  no_expiry:      "Bez vypršení",
};

const VALIDITY_STATUS_COLORS: Record<string, string> = {
  valid:          "bg-green-100 text-green-700",
  expiring_soon:  "bg-amber-100 text-amber-700",
  expired:        "bg-red-100 text-red-700",
  no_expiry:      "bg-gray-100 text-gray-500",
};

// ── Schéma formulářů ─────────────────────────────────────────────────────────

const preventiveSchema = z.object({
  employee_id:    z.string().uuid("Zaměstnanec je povinný"),
  exam_type:      z.enum(["vstupni", "periodicka", "vystupni", "mimoradna"]),
  exam_date:      z.string().min(1, "Datum prohlídky je povinné"),
  result:         z.string().optional(),
  valid_months:   z.union([z.coerce.number().int().min(1).max(120), z.literal("")]).optional(),
  physician_name: z.string().optional(),
  notes:          z.string().optional(),
});

const odbornaSchema = z.object({
  employee_id:    z.string().uuid("Zaměstnanec je povinný"),
  specialty:      z.string().min(1, "Typ vyšetření je povinný"),
  exam_date:      z.string().min(1, "Datum prohlídky je povinné"),
  result:         z.string().optional(),
  valid_months:   z.union([z.coerce.number().int().min(1).max(120), z.literal("")]).optional(),
  physician_name: z.string().optional(),
  notes:          z.string().optional(),
});

type PreventiveFormData = z.infer<typeof preventiveSchema>;
type OdbornaFormData = z.infer<typeof odbornaSchema>;

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Formulář pro periodické (preventivní) ────────────────────────────────────

function PreventiveExamForm({
  defaultValues, onSubmit, isSubmitting, serverError, employees, isEdit,
}: {
  defaultValues?: Partial<PreventiveFormData>;
  onSubmit: (data: PreventiveFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  employees: Employee[];
  isEdit: boolean;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<PreventiveFormData>({
    resolver: zodResolver(preventiveSchema),
    defaultValues: defaultValues ?? { exam_type: "periodicka" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
            <option value="">— Vyberte zaměstnance —</option>
            {employees.map(e => (
              <option key={e.id} value={e.id}>{e.last_name} {e.first_name}</option>
            ))}
          </select>
          {errors.employee_id && <p className="text-xs text-red-600">{errors.employee_id.message}</p>}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="exam_type">Typ prohlídky *</Label>
          <select id="exam_type" {...register("exam_type")} className={SELECT_CLS}>
            {PREVENTIVE_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="exam_date">Datum prohlídky *</Label>
          <Input id="exam_date" type="date" {...register("exam_date")} />
          {errors.exam_date && <p className="text-xs text-red-600">{errors.exam_date.message}</p>}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="result">Výsledek</Label>
        <select id="result" {...register("result")} className={SELECT_CLS}>
          <option value="">— Nezadáno —</option>
          {EXAM_RESULTS.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Platnost (měsíce)</Label>
          <Input id="valid_months" type="number" min="1" max="120" placeholder="48 / 24 / 12" {...register("valid_months")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="physician_name">Lékař (PLS)</Label>
          <Input id="physician_name" placeholder="MUDr. ..." {...register("physician_name")} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky</Label>
        <textarea
          id="notes" {...register("notes")} rows={2}
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

// ── Formulář pro odborné prohlídky ───────────────────────────────────────────

function OdbornaExamForm({
  defaultValues, onSubmit, isSubmitting, serverError, employees, specialties, isEdit,
}: {
  defaultValues?: Partial<OdbornaFormData>;
  onSubmit: (data: OdbornaFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  employees: Employee[];
  specialties: SpecialtyCatalogEntry[];
  isEdit: boolean;
}) {
  const { register, handleSubmit, watch, formState: { errors } } = useForm<OdbornaFormData>({
    resolver: zodResolver(odbornaSchema),
    defaultValues,
  });
  const selectedSpec = watch("specialty");
  const specInfo = specialties.find(s => s.key === selectedSpec);

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
            <option value="">— Vyberte zaměstnance —</option>
            {employees.map(e => (
              <option key={e.id} value={e.id}>{e.last_name} {e.first_name}</option>
            ))}
          </select>
          {errors.employee_id && <p className="text-xs text-red-600">{errors.employee_id.message}</p>}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="specialty">Typ odborného vyšetření *</Label>
        <select id="specialty" {...register("specialty")} className={SELECT_CLS}>
          <option value="">— Vyberte typ —</option>
          {specialties.map(s => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
        {errors.specialty && <p className="text-xs text-red-600">{errors.specialty.message}</p>}
        {specInfo && (
          <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
            <strong>{specInfo.purpose}.</strong> Typicky: {specInfo.examples}.
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="exam_date">Datum vyšetření *</Label>
        <Input id="exam_date" type="date" {...register("exam_date")} />
        {errors.exam_date && <p className="text-xs text-red-600">{errors.exam_date.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="result">Výsledek</Label>
        <select id="result" {...register("result")} className={SELECT_CLS}>
          <option value="">— Nezadáno —</option>
          {EXAM_RESULTS.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="valid_months">Platnost (měsíce)</Label>
          <Input id="valid_months" type="number" min="1" max="120" placeholder="dle kategorie práce" {...register("valid_months")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="physician_name">Lékař / specialista</Label>
          <Input id="physician_name" placeholder="MUDr. ..." {...register("physician_name")} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Poznámky</Label>
        <textarea
          id="notes" {...register("notes")} rows={2}
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

// ── Generovat vstupní (auto) ─────────────────────────────────────────────────

function GenerateInitialDialog({
  open, onClose, employees,
}: {
  open: boolean;
  onClose: () => void;
  employees: Employee[];
}) {
  const qc = useQueryClient();
  const [employeeId, setEmployeeId] = useState("");
  const [result, setResult] = useState<{ created: number; skipped_specialties: string[]; work_category: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.post<{ created: number; exam_ids: string[]; skipped_specialties: string[]; work_category: string | null }>(
      "/medical-exams/generate-initial", { employee_id: employeeId },
    ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setResult({
        created: data.created,
        skipped_specialties: data.skipped_specialties,
        work_category: data.work_category,
      });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function reset() {
    setEmployeeId(""); setResult(null); setError(null);
  }

  return (
    <Dialog
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="Auto-generovat vstupní + odborné prohlídky"
      size="md"
    >
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Podle kategorie práce zaměstnance se automaticky vytvoří draft záznam
          vstupní prohlídky a všech odborných vyšetření vyžadovaných pro jeho
          kategorii. OZO je následně doplní po skutečné prohlídce.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="gen-employee">Zaměstnanec *</Label>
          <select
            id="gen-employee"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="">— Vyberte zaměstnance —</option>
            {employees.map(e => (
              <option key={e.id} value={e.id}>{e.last_name} {e.first_name}</option>
            ))}
          </select>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800">
            <p>
              <strong>Vytvořeno {result.created} prohlídek.</strong>
              {result.work_category && ` Použita kategorie práce ${result.work_category}.`}
            </p>
            {result.skipped_specialties.length > 0 && (
              <p className="text-xs mt-1">
                Přeskočeno (už existuje): {result.skipped_specialties.join(", ")}
              </p>
            )}
            {!result.work_category && (
              <p className="text-xs mt-1 text-amber-700">
                Pozor: zaměstnanec nemá přiřazenou pozici nebo pozice nemá kategorii.
                Vytvořila se jen vstupní prohlídka.
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => { reset(); onClose(); }}>
            Zavřít
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!employeeId}
          >
            <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Vygenerovat
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

// ── Stránka ──────────────────────────────────────────────────────────────────

export default function MedicalExamsPage() {
  const qc = useQueryClient();
  const [validityFilter, setValidityFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<"all" | "preventivni" | "odborna">("all");
  const [editExam, setEditExam] = useState<MedicalExam | null>(null);
  const [createPreventiveOpen, setCreatePreventiveOpen] = useState(false);
  const [createOdbornaOpen, setCreateOdbornaOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: examsRaw = [], isLoading } = useQuery<MedicalExam[]>({
    queryKey: ["medical-exams", validityFilter, categoryFilter],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (validityFilter) qs.set("validity_status", validityFilter);
      if (categoryFilter !== "all") qs.set("exam_category", categoryFilter);
      return api.get(`/medical-exams${qs.toString() ? `?${qs.toString()}` : ""}`);
    },
  });

  const { sortedItems: exams, sortKey, sortDir, toggleSort } =
    useTableSort<MedicalExam>(examsRaw, "exam_date", "desc");

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: specialtyCatalog } = useQuery<{ specialties: SpecialtyCatalogEntry[] }>({
    queryKey: ["medical-specialty-catalog"],
    queryFn: () => api.get("/medical-exams/specialty-catalog"),
    staleTime: Infinity,
  });

  const createPreventiveMutation = useMutation({
    mutationFn: (data: PreventiveFormData) => api.post("/medical-exams", {
      ...data,
      exam_category: "preventivni",
      result: data.result || null,
      valid_months: data.valid_months === "" ? null : data.valid_months,
      physician_name: data.physician_name || null,
      notes: data.notes || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setCreatePreventiveOpen(false);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const createOdbornaMutation = useMutation({
    mutationFn: (data: OdbornaFormData) => api.post("/medical-exams", {
      ...data,
      exam_category: "odborna",
      exam_type: "odborna",
      result: data.result || null,
      valid_months: data.valid_months === "" ? null : data.valid_months,
      physician_name: data.physician_name || null,
      notes: data.notes || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setCreateOdbornaOpen(false);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PreventiveFormData & OdbornaFormData> }) =>
      api.patch(`/medical-exams/${id}`, {
        ...data,
        result: data.result || null,
        valid_months: data.valid_months === "" ? null : data.valid_months,
        physician_name: data.physician_name || null,
        notes: data.notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setEditExam(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/medical-exams/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical-exams"] }),
  });

  const uploadReportMutation = useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      const csrf = csrfMatch ? decodeURIComponent(csrfMatch[1]) : null;
      const headers: Record<string, string> = {};
      if (csrf) headers["X-CSRF-Token"] = csrf;
      const res = await fetch(`/api/v1/medical-exams/${id}/report`, {
        method: "POST", headers, body: formData, credentials: "same-origin",
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { const err = await res.json(); if (typeof err.detail === "string") detail = err.detail; } catch {}
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical-exams"] }),
  });

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  function getResultLabel(r: string | null) {
    if (!r) return "—";
    return EXAM_RESULTS.find(x => x.value === r)?.label || r;
  }

  function getTypeLabel(exam: MedicalExam) {
    if (exam.exam_category === "odborna") {
      return exam.specialty_label || exam.specialty || "Odborná";
    }
    return PREVENTIVE_TYPES.find(t => t.value === exam.exam_type)?.label || exam.exam_type;
  }

  function handleReportUpload(examId: string, e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadReportMutation.mutate({ id: examId, file });
    e.target.value = "";
  }

  return (
    <div>
      <Header
        title="Lékařské prohlídky"
        actions={
          <div className="flex items-center gap-2">
            <Tooltip label="Auto-vygenerovat vstupní + odborné podle kategorie práce">
              <Button variant="outline" size="sm" onClick={() => setGenerateOpen(true)}>
                <Sparkles className="h-4 w-4 mr-1.5" /> Generovat vstupní
              </Button>
            </Tooltip>
            <Button onClick={() => { setServerError(null); setCreatePreventiveOpen(true); }} size="sm">
              <Stethoscope className="h-4 w-4 mr-1.5" /> Přidat periodickou prohlídku
            </Button>
            <Button onClick={() => { setServerError(null); setCreateOdbornaOpen(true); }} size="sm" variant="outline">
              <Activity className="h-4 w-4 mr-1.5" /> Přidat odbornou prohlídku
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-4">
        {/* Tab: kategorie */}
        <div className="flex items-center gap-2 border-b border-gray-200 pb-2">
          {([
            { val: "all",          label: "Vše" },
            { val: "preventivni",  label: "Preventivní (vstupní/periodické/výstupní/mimořádné)" },
            { val: "odborna",      label: "Odborné" },
          ] as const).map(({ val, label }) => (
            <button
              key={val}
              onClick={() => setCategoryFilter(val)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                categoryFilter === val
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filtry validity */}
        <div className="flex items-center gap-2">
          {(["", "valid", "expiring_soon", "expired"] as const).map(val => (
            <button
              key={val}
              onClick={() => setValidityFilter(val)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                validityFilter === val
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200",
              )}
            >
              {val === "" ? "Všechny" : VALIDITY_STATUS_LABELS[val]}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{exams.length} záznamů</span>
          <Tooltip label="Stáhnout kompletní přehled prohlídek jako PDF">
            <Button
              variant="outline" size="sm"
              onClick={() => window.open("/api/v1/medical-exams/export/pdf", "_blank")}
            >
              <Download className="h-3.5 w-3.5 mr-1" /> Přehled PDF
            </Button>
          </Tooltip>
        </div>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-0">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-12 animate-pulse bg-gray-50 mx-4 my-2 rounded" />
                ))}
              </div>
            ) : exams.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Stethoscope className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné lékařské prohlídky</p>
                <p className="text-xs mt-1">Přidejte první prohlídku tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <SortableHeader sortKey="employee_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Zaměstnanec</SortableHeader>
                      <SortableHeader sortKey="exam_category" current={sortKey} dir={sortDir} onSort={toggleSort}>Druh</SortableHeader>
                      <SortableHeader sortKey="exam_date" current={sortKey} dir={sortDir} onSort={toggleSort}>Datum</SortableHeader>
                      <SortableHeader sortKey="valid_until" current={sortKey} dir={sortDir} onSort={toggleSort}>Platí do</SortableHeader>
                      <SortableHeader sortKey="result" current={sortKey} dir={sortDir} onSort={toggleSort}>Výsledek</SortableHeader>
                      <SortableHeader sortKey="physician_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Lékař</SortableHeader>
                      <SortableHeader sortKey="validity_status" current={sortKey} dir={sortDir} onSort={toggleSort}>Stav</SortableHeader>
                      <th className="py-3 px-4">Zpráva</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {exams.map(exam => (
                      <tr key={exam.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-medium text-gray-900">
                            {exam.employee_name || "—"}
                          </div>
                          {exam.employee_personal_id && (
                            <div className="text-xs text-gray-400">
                              RČ: {exam.employee_personal_id}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            exam.exam_category === "odborna"
                              ? "bg-purple-100 text-purple-700"
                              : "bg-blue-100 text-blue-700",
                          )}>
                            {getTypeLabel(exam)}
                          </span>
                          {exam.work_category && (
                            <span className="ml-1 text-[10px] text-gray-400">
                              kat. {exam.work_category}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(exam.exam_date)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(exam.valid_until)}</td>
                        <td className="py-3 px-4 text-gray-600 text-xs">{getResultLabel(exam.result)}</td>
                        <td className="py-3 px-4 text-gray-600 text-xs">{exam.physician_name || "—"}</td>
                        <td className="py-3 px-4">
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            VALIDITY_STATUS_COLORS[exam.validity_status],
                          )}>
                            {VALIDITY_STATUS_LABELS[exam.validity_status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {exam.has_report ? (
                            <Tooltip label="Otevřít zprávu z prohlídky">
                              <a
                                href={`/api/v1/medical-exams/${exam.id}/report/file`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex rounded p-1 text-green-600 hover:bg-green-50"
                                aria-label="Otevřít zprávu"
                              >
                                <FileText className="h-4 w-4" />
                              </a>
                            </Tooltip>
                          ) : (
                            <Tooltip label="Nahrát zprávu (PDF/sken)">
                              <label
                                className="inline-flex cursor-pointer rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                aria-label="Nahrát zprávu"
                              >
                                <Upload className="h-4 w-4" />
                                <input
                                  type="file"
                                  accept="application/pdf,image/png,image/jpeg,image/webp,image/heic,.pdf,.heic"
                                  className="hidden"
                                  onChange={(e) => handleReportUpload(exam.id, e)}
                                />
                              </label>
                            </Tooltip>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <Tooltip label="Žádanka pro PLS (PDF)">
                              <button
                                onClick={() => window.open(`/api/v1/medical-exams/${exam.id}/referral.pdf`, "_blank")}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                aria-label="Žádanka"
                              >
                                <FileText className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
                            <Tooltip label="Upravit záznam">
                              <button
                                onClick={() => { setServerError(null); setEditExam(exam); }}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                aria-label="Upravit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
                            <Tooltip label="Archivovat (smazání zakázáno legislativou)">
                              <button
                                onClick={() => {
                                  if (confirm(`Archivovat prohlídku: ${exam.employee_name}?`))
                                    deleteMutation.mutate(exam.id);
                                }}
                                className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                aria-label="Archivovat"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
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

      {/* Dialog: Přidat periodickou */}
      <Dialog
        open={createPreventiveOpen}
        onClose={() => setCreatePreventiveOpen(false)}
        title="Přidat periodickou prohlídku"
        size="md"
      >
        <PreventiveExamForm
          onSubmit={(data) => { setServerError(null); createPreventiveMutation.mutate(data); }}
          isSubmitting={createPreventiveMutation.isPending}
          serverError={serverError}
          employees={employees}
          isEdit={false}
        />
      </Dialog>

      {/* Dialog: Přidat odbornou */}
      <Dialog
        open={createOdbornaOpen}
        onClose={() => setCreateOdbornaOpen(false)}
        title="Přidat odbornou prohlídku"
        size="md"
      >
        <OdbornaExamForm
          onSubmit={(data) => { setServerError(null); createOdbornaMutation.mutate(data); }}
          isSubmitting={createOdbornaMutation.isPending}
          serverError={serverError}
          employees={employees}
          specialties={specialtyCatalog?.specialties ?? []}
          isEdit={false}
        />
      </Dialog>

      {/* Dialog: Upravit (univerzální podle kategorie) */}
      <Dialog
        open={!!editExam}
        onClose={() => setEditExam(null)}
        title={editExam
          ? `Upravit ${editExam.exam_category === "odborna" ? "odbornou" : "periodickou"} prohlídku — ${editExam.employee_name ?? ""}`
          : ""}
        size="md"
      >
        {editExam && editExam.exam_category === "preventivni" && (
          <PreventiveExamForm
            defaultValues={{
              employee_id:    editExam.employee_id,
              exam_type:      (["vstupni", "periodicka", "vystupni", "mimoradna"].includes(editExam.exam_type)
                                ? editExam.exam_type
                                : "periodicka") as "vstupni" | "periodicka" | "vystupni" | "mimoradna",
              exam_date:      editExam.exam_date,
              result:         editExam.result ?? "",
              valid_months:   editExam.valid_months ?? "",
              physician_name: editExam.physician_name ?? "",
              notes:          editExam.notes ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editExam.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            employees={employees}
            isEdit={true}
          />
        )}
        {editExam && editExam.exam_category === "odborna" && (
          <OdbornaExamForm
            defaultValues={{
              employee_id:    editExam.employee_id,
              specialty:      editExam.specialty ?? "",
              exam_date:      editExam.exam_date,
              result:         editExam.result ?? "",
              valid_months:   editExam.valid_months ?? "",
              physician_name: editExam.physician_name ?? "",
              notes:          editExam.notes ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editExam.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            employees={employees}
            specialties={specialtyCatalog?.specialties ?? []}
            isEdit={true}
          />
        )}
      </Dialog>

      <GenerateInitialDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        employees={employees}
      />
    </div>
  );
}
