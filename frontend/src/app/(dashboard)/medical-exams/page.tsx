"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Pencil, Trash2, Download, FileText, Upload, Sparkles,
  Stethoscope, Activity, Settings,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useTableSort } from "@/lib/use-table-sort";
import { SortableHeader } from "@/components/ui/sortable-header";
import { PeriodicitySettingsModal } from "@/components/medical-exams/periodicity-settings-modal";
import type { MedicalExam, Employee, SpecialtyCatalogEntry } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { SearchableSelect } from "@/components/ui/searchable-select";
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
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<PreventiveFormData>({
    resolver: zodResolver(preventiveSchema),
    defaultValues: defaultValues ?? { exam_type: "periodicka" },
  });
  // Skrytá registrace pole — zod validace běží, ale UI rendrujeme přes SearchableSelect
  register("employee_id");
  const empId = watch("employee_id");

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <SearchableSelect
            id="employee_id"
            required
            placeholder="— Vyberte zaměstnance —"
            value={empId || null}
            onChange={(v) => setValue("employee_id", v ?? "", { shouldValidate: true })}
            options={employees.map((e) => ({
              value: e.id,
              label: `${e.last_name} ${e.first_name}`,
              hint: e.personal_number || undefined,
            }))}
          />
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
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<OdbornaFormData>({
    resolver: zodResolver(odbornaSchema),
    defaultValues,
  });
  const selectedSpec = watch("specialty");
  const specInfo = specialties.find(s => s.key === selectedSpec);
  register("employee_id");
  const empId = watch("employee_id");

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <SearchableSelect
            id="employee_id"
            required
            placeholder="— Vyberte zaměstnance —"
            value={empId || null}
            onChange={(v) => setValue("employee_id", v ?? "", { shouldValidate: true })}
            options={employees.map((e) => ({
              value: e.id,
              label: `${e.last_name} ${e.first_name}`,
              hint: e.personal_number || undefined,
            }))}
          />
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

interface BulkGenerateResult {
  total_employees: number;
  processed: number;
  skipped_throttle: number;
  skipped_failed: number;
  total_exams_created: number;
  throttle_minutes: number;
}

function GenerateBulkDialog({
  open, onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [result, setResult] = useState<BulkGenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.post<BulkGenerateResult>("/medical-exams/generate-all", {}),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setResult(data);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function reset() {
    setResult(null); setError(null);
  }

  return (
    <Dialog
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="Generovat prohlídky pro všechny zaměstnance"
      size="md"
    >
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          Systém projde všechny aktivní zaměstnance a u každého ověří, zda má
          aktuální vstupní prohlídku a všechny odborné prohlídky vyžadované
          jeho rizikovými faktory na pozici (z RFA). Chybějící draft záznamy
          se vytvoří automaticky. Periodicita se odvozuje z ratingu konkrétního
          faktoru a věku zaměstnance (vyhláška 79/2013 Sb.).
        </p>
        <p className="text-xs text-gray-500 italic">
          Throttling: zaměstnanec, který byl zkontrolován v posledních 30 minutách,
          se přeskočí. Bezpečné spustit opakovaně.
        </p>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md bg-green-50 border border-green-200 px-3 py-3 text-sm text-green-800 space-y-1">
            <p>
              <strong>Zpracováno {result.processed} z {result.total_employees} zaměstnanců.</strong>
            </p>
            <p>Vytvořeno celkem {result.total_exams_created} nových prohlídek.</p>
            {result.skipped_throttle > 0 && (
              <p className="text-xs">
                Přeskočeno (zkontrolováno v posledních {result.throttle_minutes} minutách):
                {" "}{result.skipped_throttle}
              </p>
            )}
            {result.skipped_failed > 0 && (
              <p className="text-xs text-amber-700">
                Selhalo: {result.skipped_failed} (viz log)
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
          >
            <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Spustit kontrolu
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
  // Active/archived toggle. Default 'active' = záznamy, kterými musí OZO řešit;
  // archivované jsou ty, které reconcile zarchivoval po snížení rizik.
  const [statusFilter, setStatusFilter] = useState<"active" | "archived">("active");
  // Column filters
  const [filterEmployee, setFilterEmployee] = useState<string>("");
  const [filterExamType, setFilterExamType] = useState<string>("");
  const [filterSpecialty, setFilterSpecialty] = useState<string>("");
  const [filterPhysician, setFilterPhysician] = useState<string>("");
  const [editExam, setEditExam] = useState<MedicalExam | null>(null);
  const [createPreventiveOpen, setCreatePreventiveOpen] = useState(false);
  const [createOdbornaOpen, setCreateOdbornaOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [periodicityOpen, setPeriodicityOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: examsRaw = [], isLoading } = useQuery<MedicalExam[]>({
    queryKey: ["medical-exams", validityFilter, categoryFilter, statusFilter],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (validityFilter) qs.set("validity_status", validityFilter);
      if (categoryFilter !== "all") qs.set("exam_category", categoryFilter);
      qs.set("me_status", statusFilter);
      return api.get(`/medical-exams${qs.toString() ? `?${qs.toString()}` : ""}`);
    },
  });

  // Pro počty u filter chips — fetch BEZ filtrů. (Ignoruje me_status,
  // takže active + archived spočítáme z jednoho fetche pomocí dvou volání.)
  const { data: examsAllActive = [] } = useQuery<MedicalExam[]>({
    queryKey: ["medical-exams", "all", "active"],
    queryFn: () => api.get("/medical-exams?me_status=active"),
    staleTime: 60_000,
  });
  const { data: examsAllArchived = [] } = useQuery<MedicalExam[]>({
    queryKey: ["medical-exams", "all", "archived"],
    queryFn: () => api.get("/medical-exams?me_status=archived"),
    staleTime: 60_000,
  });
  const examsAll = useMemo(
    () => (statusFilter === "active" ? examsAllActive : examsAllArchived),
    [statusFilter, examsAllActive, examsAllArchived],
  );
  const validityCounts = useMemo(() => ({
    all: examsAll.length,
    valid: examsAll.filter((e) => e.validity_status === "valid").length,
    expiring_soon: examsAll.filter((e) => e.validity_status === "expiring_soon").length,
    expired: examsAll.filter((e) => e.validity_status === "expired").length,
  }), [examsAll]);
  const categoryCounts = useMemo(() => ({
    all: examsAll.length,
    preventivni: examsAll.filter((e) => e.exam_category === "preventivni").length,
    odborna: examsAll.filter((e) => e.exam_category === "odborna").length,
  }), [examsAll]);
  const statusCounts = useMemo(() => ({
    active: examsAllActive.length,
    archived: examsAllArchived.length,
  }), [examsAllActive, examsAllArchived]);

  // Apply column filters klient-side (po sortu)
  const examsFiltered = useMemo(() => {
    const empNeedle = filterEmployee.trim().toLowerCase();
    const physNeedle = filterPhysician.trim().toLowerCase();
    return examsRaw.filter((e) => {
      if (empNeedle && !(e.employee_name ?? "").toLowerCase().includes(empNeedle)) return false;
      if (filterExamType && e.exam_type !== filterExamType) return false;
      if (filterSpecialty && e.specialty !== filterSpecialty) return false;
      if (physNeedle && !(e.physician_name ?? "").toLowerCase().includes(physNeedle)) return false;
      return true;
    });
  }, [examsRaw, filterEmployee, filterExamType, filterSpecialty, filterPhysician]);

  const { sortedItems: exams, sortKey, sortDir, toggleSort } =
    useTableSort<MedicalExam>(examsFiltered, "exam_date", "desc");

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
            <Tooltip label="Projde všechny zaměstnance a vytvoří chybějící prohlídky podle RFA">
              <Button variant="outline" size="sm" onClick={() => setGenerateOpen(true)}>
                <Sparkles className="h-4 w-4 mr-1.5" /> Generovat prohlídky
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
        {/* Tab: kategorie + tlačítko Nastavení (úprava period) */}
        <div className="flex items-center gap-2 border-b border-gray-200 pb-2">
          {([
            { val: "all",          label: "Vše",                                                    count: categoryCounts.all },
            { val: "preventivni",  label: "Preventivní (vstupní/periodické/výstupní/mimořádné)",   count: categoryCounts.preventivni },
            { val: "odborna",      label: "Odborné",                                                count: categoryCounts.odborna },
          ] as const).map(({ val, label, count }) => (
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
              {label} ({count})
            </button>
          ))}
          <button
            type="button"
            onClick={() => setPeriodicityOpen(true)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Upravit periody lékařských prohlídek pro tenant"
          >
            <Settings className="h-3.5 w-3.5" />
            Nastavení
          </button>
        </div>

        {/* Filtry validity + status (active/archived) */}
        <div className="flex items-center gap-2 flex-wrap">
          {([
            { val: "",              label: "Všechny",      count: validityCounts.all },
            { val: "valid",         label: VALIDITY_STATUS_LABELS.valid,         count: validityCounts.valid },
            { val: "expiring_soon", label: VALIDITY_STATUS_LABELS.expiring_soon, count: validityCounts.expiring_soon },
            { val: "expired",       label: VALIDITY_STATUS_LABELS.expired,       count: validityCounts.expired },
          ] as const).map(({ val, label, count }) => (
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
              {label} ({count})
            </button>
          ))}

          {/* Aktivní / Archivované toggle — napravo. Archivované jsou prohlídky,
              které reconcile zarchivoval po snížení rizik na pozici. Default 'active'
              aby OZO viděl jen to, co opravdu musí řešit. */}
          <div className="ml-auto flex items-center gap-0 rounded-md border border-gray-200 dark:border-gray-700 overflow-hidden">
            {(["active", "archived"] as const).map(s => (
              <button
                key={s}
                type="button"
                onClick={() => setStatusFilter(s)}
                className={cn(
                  "px-3 py-1 text-xs font-medium transition-colors",
                  statusFilter === s
                    ? s === "archived"
                      ? "bg-gray-700 text-white"
                      : "bg-emerald-600 text-white"
                    : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700",
                )}
                title={
                  s === "active"
                    ? "Záznamy, které platí — je potřeba je řešit"
                    : "Záznamy archivované (např. po snížení rizik na pozici)"
                }
              >
                {s === "active"
                  ? `Aktivní prohlídky (${statusCounts.active})`
                  : `Archivované prohlídky (${statusCounts.archived})`}
              </button>
            ))}
          </div>

          <span className="text-xs text-gray-400">{exams.length} záznamů</span>
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
                      <SortableHeader sortKey="employee_personal_number" current={sortKey} dir={sortDir} onSort={toggleSort}>Os. č.</SortableHeader>
                      <SortableHeader sortKey="exam_category" current={sortKey} dir={sortDir} onSort={toggleSort}>Druh</SortableHeader>
                      <SortableHeader sortKey="exam_date" current={sortKey} dir={sortDir} onSort={toggleSort}>Datum</SortableHeader>
                      <SortableHeader sortKey="valid_until" current={sortKey} dir={sortDir} onSort={toggleSort}>Platí do</SortableHeader>
                      <SortableHeader sortKey="result" current={sortKey} dir={sortDir} onSort={toggleSort}>Výsledek</SortableHeader>
                      <SortableHeader sortKey="physician_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Lékař</SortableHeader>
                      <SortableHeader sortKey="validity_status" current={sortKey} dir={sortDir} onSort={toggleSort}>Stav</SortableHeader>
                      <th className="py-3 px-4">Zpráva</th>
                      <th className="py-3 px-4" />
                    </tr>
                    {/* Column filtry — text/dropdown per sloupec */}
                    <tr className="border-b border-gray-100 bg-white">
                      <th className="py-1.5 px-2">
                        <input
                          type="text"
                          value={filterEmployee}
                          onChange={(e) => setFilterEmployee(e.target.value)}
                          placeholder="Hledat jméno…"
                          className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </th>
                      <th className="py-1.5 px-2" />{/* Os. č. — bez filtru, lze sortovat */}
                      <th className="py-1.5 px-2">
                        <select
                          value={filterExamType}
                          onChange={(e) => setFilterExamType(e.target.value)}
                          className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        >
                          <option value="">Vše</option>
                          <option value="vstupni">Vstupní</option>
                          <option value="periodicka">Periodická</option>
                          <option value="vystupni">Výstupní</option>
                          <option value="mimoradna">Mimořádná</option>
                          <option value="odborna">Odborná</option>
                        </select>
                      </th>
                      <th className="py-1.5 px-2" />
                      <th className="py-1.5 px-2" />
                      <th className="py-1.5 px-2" />
                      <th className="py-1.5 px-2">
                        <input
                          type="text"
                          value={filterPhysician}
                          onChange={(e) => setFilterPhysician(e.target.value)}
                          placeholder="Hledat lékaře…"
                          className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </th>
                      <th className="py-1.5 px-2">
                        <select
                          value={filterSpecialty}
                          onChange={(e) => setFilterSpecialty(e.target.value)}
                          className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                          title="Filtr odbornosti (jen u odborných prohlídek)"
                        >
                          <option value="">Vše</option>
                          {(specialtyCatalog?.specialties ?? []).map((s) => (
                            <option key={s.key} value={s.key}>{s.label}</option>
                          ))}
                        </select>
                      </th>
                      <th className="py-1.5 px-2" />
                      <th className="py-1.5 px-2" />
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
                        <td className="py-3 px-4 text-xs font-mono text-gray-600">
                          {exam.employee_personal_number || "—"}
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

      <GenerateBulkDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
      />

      <PeriodicitySettingsModal
        open={periodicityOpen}
        onClose={() => setPeriodicityOpen(false)}
      />
    </div>
  );
}
