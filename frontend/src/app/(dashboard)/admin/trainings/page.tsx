"use client";

/**
 * Platform admin — globální školení (marketplace).
 * Admin vytváří šablony které jsou pak viditelné všem tenantům.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Pencil, Trash2, BookOpen, Loader2, AlertTriangle,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";

interface GlobalTraining {
  id: string;
  title: string;
  training_type: "bozp" | "po" | "other";
  trainer_kind: "ozo_bozp" | "ozo_po" | "employer";
  valid_months: number;
  notes: string | null;
  has_test: boolean;
  question_count: number;
  pass_percentage: number | null;
  is_global: boolean;
  created_at: string;
  created_by: string;
}

const TYPE_LABELS = {
  bozp: "BOZP",
  po: "Požární ochrana",
  other: "Jiné",
};

const TRAINER_LABELS = {
  ozo_bozp: "OZO BOZP",
  ozo_po: "OZO PO",
  employer: "Zaměstnavatel",
};

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

interface FormData {
  title: string;
  training_type: "bozp" | "po" | "other";
  trainer_kind: "ozo_bozp" | "ozo_po" | "employer";
  valid_months: number;
  notes: string;
}

function TrainingForm({
  defaultValues, onSubmit, isSubmitting, error,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  error: string | null;
}) {
  const [data, setData] = useState<FormData>({
    title: defaultValues?.title ?? "",
    training_type: defaultValues?.training_type ?? "bozp",
    trainer_kind: defaultValues?.trainer_kind ?? "employer",
    valid_months: defaultValues?.valid_months ?? 12,
    notes: defaultValues?.notes ?? "",
  });

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(data); }}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="title">Název *</Label>
        <Input
          id="title"
          value={data.title}
          onChange={(e) => setData({ ...data, title: e.target.value })}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="training_type">Typ školení *</Label>
          <select
            id="training_type"
            value={data.training_type}
            onChange={(e) => setData({ ...data, training_type: e.target.value as FormData["training_type"] })}
            className={SELECT_CLS}
          >
            <option value="bozp">BOZP</option>
            <option value="po">Požární ochrana</option>
            <option value="other">Jiné</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="trainer_kind">Školitel *</Label>
          <select
            id="trainer_kind"
            value={data.trainer_kind}
            onChange={(e) => setData({ ...data, trainer_kind: e.target.value as FormData["trainer_kind"] })}
            className={SELECT_CLS}
          >
            <option value="ozo_bozp">OZO BOZP</option>
            <option value="ozo_po">OZO PO</option>
            <option value="employer">Zaměstnavatel</option>
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="valid_months">Platnost (měsíce) *</Label>
        <Input
          id="valid_months"
          type="number"
          min="1"
          max="120"
          value={data.valid_months}
          onChange={(e) => setData({ ...data, valid_months: parseInt(e.target.value, 10) || 12 })}
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="notes">Popis / poznámky</Label>
        <textarea
          id="notes"
          value={data.notes}
          onChange={(e) => setData({ ...data, notes: e.target.value })}
          rows={3}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="submit" loading={isSubmitting}>Uložit</Button>
      </div>
    </form>
  );
}

export default function AdminTrainingsPage() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editTraining, setEditTraining] = useState<GlobalTraining | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: trainings = [], isLoading, isError } = useQuery<GlobalTraining[]>({
    queryKey: ["admin-global-trainings"],
    queryFn: () => api.get("/admin/global-trainings"),
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/admin/global-trainings", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-global-trainings"] });
      setCreateOpen(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FormData }) =>
      api.patch(`/admin/global-trainings/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-global-trainings"] });
      setEditTraining(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/admin/global-trainings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-global-trainings"] }),
  });

  if (isError) {
    return (
      <div>
        <Header title="Globální školení" />
        <div className="p-6">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 inline mr-2" />
            Nemáte oprávnění platform admin.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Globální školení (marketplace)"
        actions={
          <Button size="sm" onClick={() => { setError(null); setCreateOpen(true); }}>
            <Plus className="h-4 w-4 mr-1.5" /> Nové školení
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          Globální školení vytvořená zde uvidí všichni tenanti na marketplace
          (modul Školení → záložka &bdquo;Marketplace&ldquo;). Po aktivaci tenantem se
          vytvoří jeho lokální kopie, kterou pak může přiřazovat zaměstnancům.
        </div>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Načítám…
              </div>
            ) : trainings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <BookOpen className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Žádná globální školení</p>
                <p className="text-xs mt-1">Vytvoř první přes tlačítko nahoře</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Název</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Typ</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Školitel</th>
                      <th className="text-right py-3 px-4 font-semibold text-gray-700">Platnost</th>
                      <th className="text-left py-3 px-4 font-semibold text-gray-700">Test</th>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {trainings.map(t => (
                      <tr key={t.id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-900">{t.title}</td>
                        <td className="py-3 px-4 text-xs">
                          <span className="rounded-full bg-purple-100 text-purple-700 px-2 py-0.5 font-medium">
                            {TYPE_LABELS[t.training_type]}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-xs text-gray-600">{TRAINER_LABELS[t.trainer_kind]}</td>
                        <td className="py-3 px-4 text-right text-gray-600">{t.valid_months} m.</td>
                        <td className="py-3 px-4 text-xs text-gray-600">
                          {t.has_test ? `${t.question_count} otázek (${t.pass_percentage}%)` : "—"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Tooltip label="Upravit">
                              <button
                                onClick={() => { setError(null); setEditTraining(t); }}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                                aria-label="Upravit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
                            <Tooltip label="Smazat globální šablonu">
                              <button
                                onClick={() => {
                                  if (confirm(`Smazat globální školení "${t.title}"?`))
                                    deleteMutation.mutate(t.id);
                                }}
                                className="rounded p-1 text-gray-400 hover:text-red-600 hover:bg-red-50"
                                aria-label="Smazat"
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

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nové globální školení"
        size="md"
      >
        <TrainingForm
          onSubmit={(data) => { setError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          error={error}
        />
      </Dialog>

      <Dialog
        open={!!editTraining}
        onClose={() => setEditTraining(null)}
        title={editTraining ? `Upravit: ${editTraining.title}` : ""}
        size="md"
      >
        {editTraining && (
          <TrainingForm
            defaultValues={{
              title: editTraining.title,
              training_type: editTraining.training_type,
              trainer_kind: editTraining.trainer_kind,
              valid_months: editTraining.valid_months,
              notes: editTraining.notes ?? "",
            }}
            onSubmit={(data) => {
              setError(null);
              updateMutation.mutate({ id: editTraining.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            error={error}
          />
        )}
      </Dialog>
    </div>
  );
}
