"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { HardHat, Plus, Pencil, Archive, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { OOPPAssignment, Employee } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ── Konstanty ────────────────────────────────────────────────────────────────

const OOPP_TYPES: { value: string; label: string }[] = [
  { value: "head_protection",         label: "Ochrana hlavy (helmy, přilby)" },
  { value: "eye_protection",          label: "Ochrana zraku (brýle, štíty)" },
  { value: "hearing_protection",      label: "Ochrana sluchu (chrániče, zátkové)" },
  { value: "respiratory_protection",  label: "Ochrana dýchacích cest" },
  { value: "hand_protection",         label: "Ochrana rukou (rukavice)" },
  { value: "foot_protection",         label: "Ochrana nohou (boty, návleky)" },
  { value: "body_protection",         label: "Ochrana těla (oděvy, vesty)" },
  { value: "fall_protection",         label: "Ochrana proti pádu (postroje, lana)" },
  { value: "other",                   label: "Jiné OOPP" },
];

const STATUS_LABELS: Record<string, string> = {
  active:    "Aktivní",
  returned:  "Vráceno",
  discarded: "Vyřazeno",
};

const STATUS_COLORS: Record<string, string> = {
  active:    "bg-green-100 text-green-700",
  returned:  "bg-gray-100 text-gray-500",
  discarded: "bg-gray-100 text-gray-500",
};

const VALIDITY_COLORS: Record<string, string> = {
  valid:          "bg-green-100 text-green-700",
  expiring_soon:  "bg-amber-100 text-amber-700",
  expired:        "bg-red-100 text-red-700",
  no_expiry:      "bg-gray-100 text-gray-500",
};

// ── Schéma formuláře ─────────────────────────────────────────────────────────

const schema = z.object({
  employee_id:    z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
  employee_name:  z.string().min(1, "Jméno je povinné"),
  oopp_type:      z.string().min(1, "Typ OOPP je povinný"),
  oopp_name:      z.string().min(1, "Název OOPP je povinný"),
  issued_at:      z.string().min(1, "Datum vydání je povinné"),
  valid_until:    z.string().optional(),
  quantity:       z.coerce.number().int().min(1, "Minimálně 1").default(1),
  size_spec:      z.string().optional(),
  serial_number:  z.string().optional(),
  notes:          z.string().optional(),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function OOPPForm({
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
  const { register, handleSubmit, formState: { errors }, control } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? { quantity: 1 },
  });

  const selectedEmployeeId = useWatch({ control, name: "employee_id" });

  // Auto-fill employee_name when employee is selected
  const selectedEmployee = selectedEmployeeId
    ? employees.find(e => e.id === selectedEmployeeId)
    : null;

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="employee_id">Zaměstnanec / Sklad</Label>
        <select id="employee_id" {...register("employee_id")} className={SELECT_CLS}>
          <option value="">— Nevybráno / Sklad —</option>
          {employees.map(e => (
            <option key={e.id} value={e.id}>
              {e.last_name} {e.first_name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="employee_name">Jméno / Označení *</Label>
        <Input
          id="employee_name"
          placeholder={selectedEmployee ? `${selectedEmployee.last_name} ${selectedEmployee.first_name}` : "Sklad, jméno, nebo název"}
          {...register("employee_name")}
        />
        {errors.employee_name && <p className="text-xs text-red-600">{errors.employee_name.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="oopp_type">Typ OOPP *</Label>
        <select id="oopp_type" {...register("oopp_type")} className={SELECT_CLS}>
          <option value="">— Vyberte typ —</option>
          {OOPP_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        {errors.oopp_type && <p className="text-xs text-red-600">{errors.oopp_type.message}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="oopp_name">Specifická položka (např. Přilba Petzl Vertex) *</Label>
        <Input id="oopp_name" {...register("oopp_name")} />
        {errors.oopp_name && <p className="text-xs text-red-600">{errors.oopp_name.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="issued_at">Datum vydání *</Label>
          <Input id="issued_at" type="date" {...register("issued_at")} />
          {errors.issued_at && <p className="text-xs text-red-600">{errors.issued_at.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="valid_until">Platnost do</Label>
          <Input id="valid_until" type="date" {...register("valid_until")} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="quantity">Počet *</Label>
          <Input id="quantity" type="number" min="1" {...register("quantity")} />
          {errors.quantity && <p className="text-xs text-red-600">{errors.quantity.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="size_spec">Velikost</Label>
          <Input id="size_spec" placeholder="M, L, XL atd." {...register("size_spec")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="serial_number">Sériové číslo</Label>
          <Input id="serial_number" {...register("serial_number")} />
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

export default function OOPPPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [editAssignment, setEditAssignment] = useState<OOPPAssignment | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: assignments = [], isLoading } = useQuery<OOPPAssignment[]>({
    queryKey: ["oopp", statusFilter],
    queryFn: () => api.get(`/oopp${statusFilter ? `?status=${statusFilter}` : ""}`),
  });

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/oopp", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["oopp"] }); setCreateOpen(false); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormData> }) =>
      api.patch(`/oopp/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["oopp"] }); setEditAssignment(null); },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/oopp/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oopp"] }),
  });

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("cs-CZ");
  }

  function getValidityLabel(status: string): string {
    return status === "valid" ? "Platný"
         : status === "expiring_soon" ? "Expiruje brzy"
         : status === "expired" ? "Vypršel"
         : "Bez expirace";
  }

  return (
    <div>
      <Header
        title="OOPP (Osobní ochranné pomůcky)"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Nový OOPP
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="flex items-center gap-2">
          {(["", "active", "returned"] as const).map(val => (
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
              {val === "" ? "Všechny" : val === "active" ? "Aktivní" : "Vráceno"}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-400">{assignments.length} záznamů</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.open("/api/v1/oopp/export/pdf", "_blank")}
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
            ) : assignments.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <HardHat className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádný OOPP</p>
                <p className="text-xs mt-1">Přidejte položku OOPP tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Zaměstnanec</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">OOPP</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Vydáno</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Platnost</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500">Množství</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {assignments.map(assignment => (
                      <tr key={assignment.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {assignment.employee_name}
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          <div>
                            <p className="font-medium text-gray-900">{assignment.oopp_name}</p>
                            <p className="text-xs text-gray-400">{assignment.oopp_type}</p>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          {formatDate(assignment.issued_at)}
                        </td>
                        <td className="py-3 px-4">
                          {assignment.valid_until ? (
                            <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", VALIDITY_COLORS[assignment.validity_status])}>
                              {getValidityLabel(assignment.validity_status)}
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">Bez expirace</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[assignment.status])}>
                            {STATUS_LABELS[assignment.status]}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-600">
                          {assignment.quantity} {assignment.size_spec ? `(${assignment.size_spec})` : ""}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => { setServerError(null); setEditAssignment(assignment); }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Upravit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            {assignment.status === "active" && (
                              <button
                                onClick={() => {
                                  if (confirm(`Archivovat OOPP: ${assignment.oopp_name} (${assignment.employee_name})?`))
                                    archiveMutation.mutate(assignment.id);
                                }}
                                className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                                title="Archivovat"
                              >
                                <Archive className="h-3.5 w-3.5" />
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

      {/* Dialog: Nový OOPP */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nový OOPP"
        size="lg"
      >
        <OOPPForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          employees={employees}
        />
      </Dialog>

      {/* Dialog: Upravit OOPP */}
      <Dialog
        open={!!editAssignment}
        onClose={() => setEditAssignment(null)}
        title={editAssignment ? `${editAssignment.oopp_name}` : ""}
        size="lg"
      >
        {editAssignment && (
          <OOPPForm
            defaultValues={{
              employee_id:    editAssignment.employee_id ?? "",
              employee_name:  editAssignment.employee_name,
              oopp_type:      editAssignment.oopp_type,
              oopp_name:      editAssignment.oopp_name,
              issued_at:      editAssignment.issued_at,
              valid_until:    editAssignment.valid_until ?? "",
              quantity:       editAssignment.quantity,
              size_spec:      editAssignment.size_spec ?? "",
              serial_number:  editAssignment.serial_number ?? "",
              notes:          editAssignment.notes ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editAssignment.id, data });
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
