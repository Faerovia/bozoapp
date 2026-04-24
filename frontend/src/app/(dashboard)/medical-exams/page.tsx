"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Pencil, Trash2, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { MedicalExam, Employee } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const EXAM_TYPES: { value: string; label: string }[] = [
  { value: "vstupni",     label: "Vstupní" },
  { value: "periodicka",  label: "Periodická" },
  { value: "vystupni",    label: "Výstupní" },
  { value: "mimoradna",   label: "Mimořádná" },
];

const EXAM_RESULTS: { value: string; label: string }[] = [
  { value: "zpusobily",        label: "Způsobilý" },
  { value: "zpusobily_omezeni", label: "Způsobilý s omezením" },
  { value: "nezpusobily",      label: "Nezpůsobilý" },
  { value: "pozbyl_zpusobilosti", label: "Pozbyl způsobilosti" },
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

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  employee_id:   z.string().uuid("Zaměstnanec je povinný"),
  exam_type:     z.string().min(1, "Typ zkoušky je povinný"),
  exam_date:     z.string().min(1, "Datum zkoušky je povinné"),
  result:        z.string().optional().transform(v => v || null),
  valid_months:  z.string().optional().transform(v => v ? parseInt(v, 10) : null),
  doctor_name:   z.string().optional().transform(v => v || null),
  notes:         z.string().optional().transform(v => v || null),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function MedicalExamForm({
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
  isEdit: boolean;
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { exam_type: "periodicka" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!isEdit && (
        <div className="space-y-1.5">
          <Label htmlFor="employee_id">Zaměstnanec *</Label>
          <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
            <option value="">— Vyberte zaměstnance —</option>
            {employees.map(emp => (
              <option key={emp.id} value={emp.id}>
                {emp.last_name} {emp.first_name}
              </option>
            ))}
          </select>
          {errors.employee_id && <p className="text-xs text-red-600">{errors.employee_id.message}</p>}
          {employees.length === 0 && (
            <p className="text-xs text-gray-400">Nejprve vytvořte zaměstnance</p>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="exam_type">Typ zkoušky *</Label>
        <select id="exam_type" {...register("exam_type")} className={SELECT_CLS}>
          {EXAM_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        {errors.exam_type && <p className="text-xs text-red-600">{errors.exam_type.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="exam_date">Datum zkoušky *</Label>
        <Input id="exam_date" type="date" {...register("exam_date")} />
        {errors.exam_date && <p className="text-xs text-red-600">{errors.exam_date.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="result">Výsledek</Label>
        <select id="result" {...register("result")} className={SELECT_CLS}>
          <option value="">— Čeká na výsledek —</option>
          {EXAM_RESULTS.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="valid_months">Platnost (měsíce)</Label>
        <Input
          id="valid_months"
          type="number"
          min="1"
          {...register("valid_months")}
          placeholder="72"
        />
        <p className="text-xs text-gray-400">Kat. 1 = 72m, Kat. 2 = 48m, 2R/3 = 24m, Kat. 4 = 12m</p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="doctor_name">Lékař</Label>
        <Input id="doctor_name" {...register("doctor_name")} />
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

      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function MedicalExamsPage() {
  const qc = useQueryClient();
  const [validityFilter, setValidityFilter] = useState<string>("");
  const [editExam, setEditExam] = useState<MedicalExam | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: exams = [], isLoading } = useQuery<MedicalExam[]>({
    queryKey: ["medical-exams", validityFilter],
    queryFn: () => api.get(`/medical-exams${validityFilter ? `?validity_status=${validityFilter}` : ""}`),
  });

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/medical-exams", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["medical-exams"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/medical-exams/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["medical-exams"] }); setEditExam(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/medical-exams/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical-exams"] }),
  });

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  function getExamTypeLabel(type: string) {
    return EXAM_TYPES.find(t => t.value === type)?.label || type;
  }

  function getExamResultLabel(result: string | null) {
    if (!result) return "—";
    return EXAM_RESULTS.find(r => r.value === result)?.label || result;
  }

  return (
    <div>
      <Header
        title="Zdravotnické zkoušky"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat zkoušku
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2">
          {(["", "valid", "expiring_soon", "expired"] as const).map(val => (
            <button
              key={val}
              onClick={() => setValidityFilter(val)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                validityFilter === val
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              )}
            >
              {val === "" ? "Všechny" : VALIDITY_STATUS_LABELS[val]}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{exams.length} záznamů</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open("/api/v1/medical-exams/export/pdf", "_blank")}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            PDF
          </Button>
        </div>

        {/* Tabulka */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-0 divide-y divide-gray-50">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-12 animate-pulse bg-gray-50 mx-4 my-2 rounded" />
                ))}
              </div>
            ) : exams.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <Plus className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné zdravotnické zkoušky</p>
                <p className="text-xs mt-1">Přidejte první zkoušku tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zaměstnanec</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Datum</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Výsledek</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Platnost do</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {exams.map(exam => (
                      <tr key={exam.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {exam.employee_name || "—"}
                        </td>
                        <td className="py-3 px-4 text-gray-600 text-xs">{getExamTypeLabel(exam.exam_type)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(exam.exam_date)}</td>
                        <td className="py-3 px-4 text-gray-600">{getExamResultLabel(exam.result)}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(exam.valid_until)}</td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", VALIDITY_STATUS_COLORS[exam.validity_status])}>
                            {VALIDITY_STATUS_LABELS[exam.validity_status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditExam(exam); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`Smazat zkoušku: ${exam.employee_name}?`))
                                  deleteMutation.mutate(exam.id);
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

      {/* Dialog: Nová zkouška */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat zdravotnickou zkoušku"
        size="md"
      >
        <MedicalExamForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          employees={employees}
          isEdit={false}
        />
      </Dialog>

      {/* Dialog: Upravit zkoušku */}
      <Dialog
        open={!!editExam}
        onClose={() => setEditExam(null)}
        title={editExam ? `Upravit zkoušku: ${editExam.employee_name}` : ""}
        size="md"
      >
        {editExam && (
          <MedicalExamForm
            defaultValues={{
              employee_id:  editExam.employee_id,
              exam_type:    editExam.exam_type,
              exam_date:    editExam.exam_date,
              result:       editExam.result ?? "",
              valid_months: editExam.valid_months ?? undefined,
              doctor_name:  editExam.doctor_name ?? "",
              notes:        editExam.notes ?? "",
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
      </Dialog>
    </div>
  );
}
