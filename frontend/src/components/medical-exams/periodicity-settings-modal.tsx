"use client";

/**
 * Modal pro úpravu period lékařských prohlídek per tenant.
 *
 * Priorita: tenant override > platform default > zákonný default.
 * UI ukazuje všechny 3 sloupce, OZO může přepsat per kategorie + věk.
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

type Category = "1" | "2" | "2R" | "3" | "4";
const CATEGORIES: Category[] = ["1", "2", "2R", "3", "4"];

interface PeriodicityRule {
  under_50: number | null;
  from_50: number | null;
}
type RulesMap = Record<Category, PeriodicityRule>;

interface SettingsResponse {
  tenant_override: RulesMap | null;
  platform_default: RulesMap | null;
  legal_default: RulesMap;
}

const EMPTY_RULES: RulesMap = {
  "1":  { under_50: null, from_50: null },
  "2":  { under_50: null, from_50: null },
  "2R": { under_50: null, from_50: null },
  "3":  { under_50: null, from_50: null },
  "4":  { under_50: null, from_50: null },
};

export function PeriodicitySettingsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<RulesMap>(EMPTY_RULES);
  const [serverError, setServerError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const { data, isLoading } = useQuery<SettingsResponse>({
    queryKey: ["medical-exam-periodicity-settings"],
    queryFn: () => api.get("/medical-exams/settings/periodicity"),
    enabled: open,
  });

  // Inicializace draftu — preferuj tenant override, jinak nech NULL (= dědí default)
  useEffect(() => {
    if (data) {
      setDraft(data.tenant_override ?? EMPTY_RULES);
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: (rules: RulesMap) =>
      api.patch("/medical-exams/settings/periodicity", rules),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["medical-exam-periodicity-settings"] });
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setServerError(null);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    },
    onError: (err) => {
      if (err instanceof ApiError) setServerError(err.detail);
      else setServerError("Chyba při ukládání");
    },
  });

  const resetMutation = useMutation({
    mutationFn: () =>
      api.patch("/medical-exams/settings/periodicity", null),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["medical-exam-periodicity-settings"] });
      qc.invalidateQueries({ queryKey: ["medical-exams"] });
      setDraft(EMPTY_RULES);
    },
  });

  function setRule(cat: Category, age: keyof PeriodicityRule, value: string) {
    const num = value === "" ? null : Number.parseInt(value, 10);
    if (value !== "" && (Number.isNaN(num) || num! < 1 || num! > 600)) return;
    setDraft((prev) => ({
      ...prev,
      [cat]: { ...prev[cat], [age]: num },
    }));
  }

  function effectiveValue(cat: Category, age: keyof PeriodicityRule): string {
    if (!data) return "";
    const tenant = data.tenant_override?.[cat]?.[age];
    if (tenant != null) return `${tenant} (tenant)`;
    const platform = data.platform_default?.[cat]?.[age];
    if (platform != null) return `${platform} (platform)`;
    const legal = data.legal_default[cat]?.[age];
    return legal != null ? `${legal} (vyhláška)` : "—";
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Periody lékařských prohlídek"
      description="Per-tenant override. Přepisuje platform default a zákonnou vyhlášku 79/2013."
      size="lg"
    >
      {isLoading ? (
        <div className="text-sm text-gray-500 py-6">Načítám…</div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 px-3 py-2 text-xs text-blue-800 dark:text-blue-200">
            Periody jsou v měsících. Prázdné pole = dědíme z platform/zákonu.
            Priorita: <strong>Tenant → Platform → Vyhláška 79/2013</strong>.
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-3 py-2 text-left">Kategorie</th>
                  <th className="px-3 py-2 text-left">Věk &lt; 50</th>
                  <th className="px-3 py-2 text-left">Věk ≥ 50</th>
                  <th className="px-3 py-2 text-left text-gray-400">Aktuálně platí</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {CATEGORIES.map((cat) => (
                  <tr key={cat}>
                    <td className="px-3 py-2 font-mono font-medium">Kat. {cat}</td>
                    <td className="px-3 py-2">
                      <Input
                        type="number"
                        min={1}
                        max={600}
                        placeholder="dědí"
                        value={draft[cat].under_50 ?? ""}
                        onChange={(e) => setRule(cat, "under_50", e.target.value)}
                        className="w-24"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        type="number"
                        min={1}
                        max={600}
                        placeholder="dědí"
                        value={draft[cat].from_50 ?? ""}
                        onChange={(e) => setRule(cat, "from_50", e.target.value)}
                        className="w-24"
                      />
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500">
                      <div>{effectiveValue(cat, "under_50")} m</div>
                      <div>{effectiveValue(cat, "from_50")} m</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {serverError && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}
          {savedFlash && (
            <div className="rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-700">
              Uloženo. Nové prohlídky budou používat aktualizované periody.
            </div>
          )}

          <div className="flex items-center justify-between pt-2 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => resetMutation.mutate()}
              loading={resetMutation.isPending}
              title="Smazat tenant override — vrátit na platform/vyhláškové defaulty"
            >
              Zrušit override
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Zavřít
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setServerError(null);
                  saveMutation.mutate(draft);
                }}
                loading={saveMutation.isPending}
              >
                Uložit
              </Button>
            </div>
          </div>
          <Label className="text-xs text-gray-400">
            Změna ovlivní jen nově generované prohlídky. Existující záznamy zůstávají.
          </Label>
        </div>
      )}
    </Dialog>
  );
}
