"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Plus, Pencil, FileText, CheckCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AccidentReport, Employee } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  draft:    "Rozpracovaný",
  final:    "Finální",
  archived: "Archivovaný",
};

const STATUS_COLORS: Record<string, string> = {
  draft:    "bg-amber-100 text-amber-700",
  final:    "bg-blue-100 text-blue-700",
  archived: "bg-gray-100 text-gray-500",
};

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  title:                z.string().min(1, "Název je povinný"),
  accident_date:        z.string().min(1, "Datum nehody je povinné"),
  accident_time:        z.string().optional(),
  location:             z.string().optional(),
  description:          z.string().optional(),
  employee_id:          z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
  injured_count:        z.coerce.number().int().min(1, "Minimálně 1").default(1),
  is_fatal:             z.boolean().default(false),
  work_absence_days:    z.union([z.coerce.number().int().min(0), z.literal("")]).optional(),
  risk_review_required: z.boolean().default(false),
  notes:                z.string().optional(),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function AccidentForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  employees,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  employees: Employee[];
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { injured_count: 1, is_fatal: false, risk_review_required: false },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="title">Název nehody *</Label>
        <Input id="title" {...register("title")} />
        {errors.title && <p className="text-xs text-red-600">{errors.title.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="accident_date">Datum nehody *</Label>
          <Input id="accident_date" type="date" {...register("accident_date")} />
          {errors.accident_date && <p className="text-xs text-red-600">{errors.accident_date.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="accident_time">Čas nehody</Label>
          <Input id="accident_time" type="time" {...register("accident_time")} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="location">Místo nehody</Label>
        <Input id="location" {...register("location")} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="description">Popis nehody</Label>
        <textarea
          id="description"
          {...register("description")}
          rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="employee_id">Zaměstnanec</Label>
        <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
          <option value="">— Nevybráno —</option>
          {employees.map(e => (
            <option key={e.id} value={e.id}>
              {e.last_name} {e.first_name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="injured_count">Počet zraněných *</Label>
          <Input id="injured_count" type="number" min="1" {...register("injured_count")} />
          {errors.injured_count && <p className="text-xs text-red-600">{errors.injured_count.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="work_absence_days">Počet dnů pracovní absence</Label>
          <Input id="work_absence_days" type="number" min="0" {...register("work_absence_days")} />
        </div>
      </div>

      <div className="space-y-2">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" {...register("is_fatal")} className="rounded" />
          <span className="text-sm font-medium">Smrtelná nehoda</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" {...register("risk_review_required")} className="rounded" />
          <span className="text-sm font-medium">Vyžaduje kontrolu rizik</span>
        </label>
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

export default function AccidentReportsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("draft");
  const [editReport, setEditReport] = useState<AccidentReport | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: reports = [], isLoading } = useQuery<AccidentReport[]>({
    queryKey: ["accident-reports", statusFilter],
    queryFn: () => api.get(`/accident-reports${statusFilter ? `?status=${statusFilter}` : ""}`),
  });

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/accident-reports", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["accident-reports"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/accident-reports/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["accident-reports"] }); setEditReport(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const finalizeMutation = useMutation({
    mutationFn: (id: string) => api.post(`/accident-reports/${id}/finalize`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accident-reports"] }),
  });

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  return (
    <div>
      <Header
        title="Zprávy o nehodách"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Nová nehoda
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2">
          {(["", "draft", "final", "archived"] as const).map(val => (
            <button
              key={val}
              onClick={() => setStatusFilter(val)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                statusFilter === val
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              )}
            >
              {val === "" ? "Všechny" : val === "draft" ? "Rozpracované" : val === "final" ? "Finální" : "Archivované"}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{reports.length} záznamů</span>
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
            ) : reports.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <AlertTriangle className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádné zprávy</p>
                <p className="text-xs mt-1">Přidejte zprávu o nehodě tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Název</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Datum</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zaměstnanec</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zranění</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {reports.map(report => (
                      <tr key={report.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">{report.title}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(report.accident_date)}</td>
                        <td className="py-3 px-4 text-gray-600">
                          {report.employee_name || "—"}
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          {report.injured_count} {report.is_fatal ? "(smrtelný)" : ""}
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[report.status])}>
                            {STATUS_LABELS[report.status]}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            {report.status === "draft" && (
                              <button
                                onClick={() => { setServerError(null); setEditReport(report); }}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                title="Upravit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                            )}
                            <button
                              onClick={() => window.open(`/api/v1/accident-reports/${report.id}/pdf`, "_blank")}
                              className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                              title="Stáhnout PDF"
                            >
                              <FileText className="h-3.5 w-3.5" />
                            </button>
                            {report.status === "draft" && (
                              <button
                                onClick={() => {
                                  if (confirm("Finalizovat tuto zprávu? Nebude již možné ji upravovat."))
                                    finalizeMutation.mutate(report.id);
                                }}
                                className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                                title="Finalizovat"
                              >
                                <CheckCircle className="h-3.5 w-3.5" />
                              </button>
                            )}
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

      {/* Dialog: Nová nehoda */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nová zpráva o nehodě"
        size="lg"
      >
        <AccidentForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          employees={employees}
        />
      </Dialog>

      {/* Dialog: Upravit nehodu */}
      <Dialog
        open={!!editReport}
        onClose={() => setEditReport(null)}
        title={editReport ? editReport.title : ""}
        size="lg"
      >
        {editReport && (
          <AccidentForm
            defaultValues={{
              title:                editReport.title,
              accident_date:        editReport.accident_date,
              accident_time:        editReport.accident_time ?? "",
              location:             editReport.location ?? "",
              description:          editReport.description ?? "",
              employee_id:          editReport.employee_id ?? "",
              injured_count:        editReport.injured_count,
              is_fatal:             editReport.is_fatal,
              work_absence_days:    editReport.work_absence_days ?? "",
              risk_review_required: editReport.risk_review_required,
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editReport.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            employees={employees}
          />
        )}
      </Dialog>
    </div>
  );
}
