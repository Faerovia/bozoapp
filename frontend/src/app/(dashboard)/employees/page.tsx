"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { UserPlus, Pencil, UserX, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Employee, EmploymentType, JobPosition, Workplace } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const EMPLOYMENT_TYPES: { value: EmploymentType; label: string }[] = [
  { value: "hpp",        label: "HPP – hlavní pracovní poměr" },
  { value: "dpp",        label: "DPP – dohoda o provedení práce" },
  { value: "dpc",        label: "DPČ – dohoda o pracovní činnosti" },
  { value: "externista", label: "Externista" },
  { value: "brigádník",  label: "Brigádník" },
];

const STATUS_LABELS: Record<string, string> = {
  active:     "Aktivní",
  terminated: "Ukončen",
  on_leave:   "Dovolená / Absence",
};

const STATUS_COLORS: Record<string, string> = {
  active:     "bg-green-100 text-green-700",
  terminated: "bg-gray-100 text-gray-500",
  on_leave:   "bg-amber-100 text-amber-700",
};

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  first_name:       z.string().min(1, "Jméno je povinné"),
  last_name:        z.string().min(1, "Příjmení je povinné"),
  employment_type:  z.enum(["hpp", "dpp", "dpc", "externista", "brigádník"] as const),
  email:            z.string().email("Neplatný email").or(z.literal("")).optional(),
  phone:            z.string().optional(),
  hired_at:         z.string().optional(),
  birth_date:       z.string().optional(),
  personal_id:      z.string().optional(),
  notes:            z.string().optional(),
  job_position_id:  z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
  workplace_id:     z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function EmployeeForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  jobPositions,
  workplaces,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  jobPositions: JobPosition[];
  workplaces: Workplace[];
}) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { employment_type: "hpp" },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="first_name">Jméno *</Label>
          <Input id="first_name" {...register("first_name")} />
          {errors.first_name && <p className="text-xs text-red-600">{errors.first_name.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="last_name">Příjmení *</Label>
          <Input id="last_name" {...register("last_name")} />
          {errors.last_name && <p className="text-xs text-red-600">{errors.last_name.message}</p>}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="employment_type">Typ úvazku *</Label>
        <select id="employment_type" {...register("employment_type")} className={SELECT_CLS}>
          {EMPLOYMENT_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...register("email")} />
          {errors.email && <p className="text-xs text-red-600">{errors.email.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Telefon</Label>
          <Input id="phone" {...register("phone")} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="hired_at">Datum nástupu</Label>
          <Input id="hired_at" type="date" {...register("hired_at")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="birth_date">Datum narození</Label>
          <Input id="birth_date" type="date" {...register("birth_date")} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="personal_id">Rodné číslo / Osobní číslo</Label>
        <Input id="personal_id" {...register("personal_id")} />
      </div>

      {/* Pracovní zařazení */}
      <div className="border-t border-gray-100 pt-4">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
          Pracovní zařazení
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="job_position_id">Pracovní pozice</Label>
            <select id="job_position_id" {...register("job_position_id")} className={SELECT_CLS}>
              <option value="">— Nevybráno —</option>
              {jobPositions.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.work_category ? ` (kat. ${p.work_category})` : ""}
                </option>
              ))}
            </select>
            {jobPositions.length === 0 && (
              <p className="text-xs text-gray-400">Nejprve vytvořte pracovní pozice</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="workplace_id">Pracoviště</Label>
            <select id="workplace_id" {...register("workplace_id")} className={SELECT_CLS}>
              <option value="">— Nevybráno —</option>
              {workplaces.map(w => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
            {workplaces.length === 0 && (
              <p className="text-xs text-gray-400">Nejprve vytvořte pracoviště</p>
            )}
          </div>
        </div>
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

export default function EmployeesPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: employees = [], isLoading } = useQuery<Employee[]>({
    queryKey: ["employees", statusFilter],
    queryFn: () => api.get(`/employees${statusFilter ? `?emp_status=${statusFilter}` : ""}`),
  });

  const { data: jobPositions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions"],
    queryFn: () => api.get("/job-positions"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces"],
    queryFn: () => api.get("/workplaces"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/employees", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["employees"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/employees/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["employees"] }); setEditEmployee(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const terminateMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/employees/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["employees"] }),
  });

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  return (
    <div>
      <Header
        title="Zaměstnanci"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <UserPlus className="h-4 w-4 mr-1.5" />
            Přidat zaměstnance
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2">
          {(["", "active", "terminated", "on_leave"] as const).map(val => (
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
              {val === "" ? "Všichni" : STATUS_LABELS[val]}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{employees.length} záznamů</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open("/api/v1/employees/export/pdf", "_blank")}
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
            ) : employees.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <UserPlus className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádní zaměstnanci</p>
                <p className="text-xs mt-1">Přidejte prvního zaměstnance tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Jméno</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Úvazek</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Status</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Email</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Nástup</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {employees.map(emp => (
                      <tr key={emp.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {emp.last_name} {emp.first_name}
                        </td>
                        <td className="py-3 px-4 text-gray-600 uppercase text-xs font-medium">
                          {emp.employment_type}
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[emp.status])}>
                            {STATUS_LABELS[emp.status]}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-600">{emp.email || "—"}</td>
                        <td className="py-3 px-4 text-gray-600">{formatDate(emp.hired_at)}</td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditEmployee(emp); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            {emp.status === "active" && (
                              <button
                                onClick={() => {
                                  if (confirm(`Ukončit pracovní poměr: ${emp.last_name} ${emp.first_name}?`))
                                    terminateMutation.mutate(emp.id);
                                }}
                                className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                                title="Ukončit"
                              >
                                <UserX className="h-3.5 w-3.5" />
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

      {/* Dialog: Nový zaměstnanec */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat zaměstnance"
        size="lg"
      >
        <EmployeeForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          jobPositions={jobPositions}
          workplaces={workplaces}
        />
      </Dialog>

      {/* Dialog: Upravit zaměstnance */}
      <Dialog
        open={!!editEmployee}
        onClose={() => setEditEmployee(null)}
        title={editEmployee ? `${editEmployee.last_name} ${editEmployee.first_name}` : ""}
        size="lg"
      >
        {editEmployee && (
          <EmployeeForm
            defaultValues={{
              first_name:      editEmployee.first_name,
              last_name:       editEmployee.last_name,
              employment_type: editEmployee.employment_type,
              email:           editEmployee.email ?? "",
              phone:           editEmployee.phone ?? "",
              hired_at:        editEmployee.hired_at ?? "",
              birth_date:      editEmployee.birth_date ?? "",
              personal_id:     editEmployee.personal_id ?? "",
              notes:           editEmployee.notes ?? "",
              job_position_id: editEmployee.job_position_id ?? "",
              workplace_id:    editEmployee.workplace_id ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editEmployee.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            jobPositions={jobPositions}
            workplaces={workplaces}
          />
        )}
      </Dialog>
    </div>
  );
}
