"use client";

/**
 * Platform admin — fakturační údaje vystavovatele (issuer).
 *
 * 16 keys v platform_settings (issuer_*, is_vat_payer, vat_rate, invoice_*).
 * Místo per-key JSON editoru tady máme přívětivý formulář s validací.
 *
 * Na rozdíl od /admin/settings/[slug] tahle stránka updatuje VÍCE klíčů
 * najednou — sekvenčním PATCH na /admin/settings/{key} za každé pole, které
 * se změnilo. Backend cache se automaticky invaliduje.
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, Loader2, AlertTriangle, RotateCcw, Building2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface PlatformSetting {
  key: string;
  value: unknown;
  description: string | null;
  updated_by: string | null;
  updated_at: string;
}

// Klíče v pořadí jak je chceme v UI; každé pole drží i typ (string/number/bool).
type FieldType = "text" | "email" | "number" | "bool" | "textarea";

interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  placeholder?: string;
  hint?: string;
  required?: boolean;
}

const FIELDS: { section: string; fields: FieldDef[] }[] = [
  {
    section: "Základní údaje",
    fields: [
      { key: "issuer_name",       label: "Název / firma *", type: "text",
        placeholder: "OZODigi s.r.o.", required: true },
      { key: "issuer_ico",        label: "IČO *", type: "text",
        placeholder: "12345678", required: true,
        hint: "8 číslic, bez mezer." },
      { key: "issuer_dic",        label: "DIČ", type: "text",
        placeholder: "CZ12345678",
        hint: "Pro plátce DPH (CZ + IČO). Neplátci nechají prázdné." },
      { key: "issuer_email",      label: "Kontaktní email *", type: "email",
        placeholder: "fakturace@bozoapp.cz",
        hint: "Příjemci faktur se mohou ozvat na tuhle adresu." },
    ],
  },
  {
    section: "Adresa sídla",
    fields: [
      { key: "issuer_address_street", label: "Ulice + č.p. *", type: "text",
        placeholder: "Dlouhá 1" },
      { key: "issuer_address_zip",    label: "PSČ *", type: "text",
        placeholder: "110 00" },
      { key: "issuer_address_city",   label: "Město *", type: "text",
        placeholder: "Praha" },
    ],
  },
  {
    section: "Bankovní spojení",
    fields: [
      { key: "issuer_bank_account", label: "Číslo účtu (CZ formát)", type: "text",
        placeholder: "123456789/0100",
        hint: "Zobrazí se na faktuře jako bankovní spojení." },
      { key: "issuer_bank_name",    label: "Název banky", type: "text",
        placeholder: "Komerční banka, a.s." },
      { key: "issuer_iban",         label: "IBAN *", type: "text",
        placeholder: "CZ6508000000192000145399",
        hint: "Povinné pro QR Pay-by-Square na faktuře." },
      { key: "issuer_swift",        label: "SWIFT / BIC", type: "text",
        placeholder: "KOMBCZPP" },
    ],
  },
  {
    section: "DPH a fakturace",
    fields: [
      { key: "is_vat_payer",          label: "Plátce DPH", type: "bool",
        hint: "Po překročení obratu (2M Kč/rok) přepneš na true. Faktura pak " +
          "obsahuje DPH řádek a název 'Faktura — daňový doklad'." },
      { key: "vat_rate",              label: "Sazba DPH (%)", type: "number",
        placeholder: "21",
        hint: "Aplikuje se jen pokud is_vat_payer=true." },
      { key: "invoice_due_days",      label: "Splatnost (dnů od vystavení)", type: "number",
        placeholder: "14",
        hint: "Standard v ČR je 14 dnů." },
      { key: "invoice_number_format", label: "Formát čísla faktury", type: "text",
        placeholder: "{year}{seq:04d}",
        hint: "Placeholdery: {year} (rok 4-místně), {seq:04d} (pořadí v daném roce)." },
      { key: "invoice_footer_note",   label: "Pata faktury", type: "textarea",
        placeholder: "Děkujeme za spolupráci.",
        hint: "Text pod tabulkou položek." },
    ],
  },
];

const ALL_KEYS = FIELDS.flatMap(s => s.fields.map(f => f.key));

function settingValueToString(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function stringToSettingValue(v: string, type: FieldType): unknown {
  if (type === "bool") return v === "true";
  if (type === "number") {
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }
  return v;
}

export default function InvoiceIssuerSettingsPage() {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [initialValues, setInitialValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const { data: settings = [], isLoading, isError } = useQuery<PlatformSetting[]>({
    queryKey: ["admin-settings"],
    queryFn: () => api.get("/admin/settings"),
  });

  // Initial load — naplníme stavy z DB
  useEffect(() => {
    if (settings.length > 0) {
      const next: Record<string, string> = {};
      for (const k of ALL_KEYS) {
        const s = settings.find(x => x.key === k);
        next[k] = settingValueToString(s?.value);
      }
      setValues(next);
      setInitialValues(next);
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: async (changes: { key: string; value: unknown }[]) => {
      // Sekvenční PATCH (settings je zřídka updatováno, paralelizace netřeba)
      for (const ch of changes) {
        await api.patch(
          `/admin/settings/${encodeURIComponent(ch.key)}`,
          { value: ch.value },
        );
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setSavedAt(new Date().toLocaleTimeString("cs-CZ"));
      setError(null);
      setInitialValues({ ...values });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba ukládání"),
  });

  const dirtyKeys = ALL_KEYS.filter(k => values[k] !== initialValues[k]);
  const isDirty = dirtyKeys.length > 0;

  function handleSave() {
    setError(null);
    const changes = dirtyKeys.map(k => {
      const fieldDef = FIELDS.flatMap(s => s.fields).find(f => f.key === k)!;
      return { key: k, value: stringToSettingValue(values[k], fieldDef.type) };
    });
    saveMutation.mutate(changes);
  }

  function handleReset() {
    setValues({ ...initialValues });
    setError(null);
  }

  if (isError) {
    return (
      <div>
        <Header title="Fakturační údaje" />
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
      <Header title="Fakturační údaje (vystavovatel)" />

      <div className="p-6 space-y-4">
        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          Tyhle údaje se objeví jako <strong>vystavovatel</strong> na každé faktuře. Bez vyplnění
          IČO, IBAN a kontaktního emailu nepůjde fakturu vystavit nebo na ní nebude QR
          platba pro Pay-by-Square.
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-gray-400 py-12 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" /> Načítám…
          </div>
        ) : (
          <>
            {FIELDS.map(({ section, fields }) => (
              <Card key={section}>
                <CardContent className="p-5 space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                    <Building2 className="h-4 w-4 text-blue-600" />
                    {section}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    {fields.map(f => (
                      <div
                        key={f.key}
                        className={f.type === "textarea" ? "col-span-2 space-y-1.5" : "space-y-1.5"}
                      >
                        <Label htmlFor={f.key}>{f.label}</Label>

                        {f.type === "bool" ? (
                          <select
                            id={f.key}
                            value={values[f.key] ?? "false"}
                            onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="false">Ne</option>
                            <option value="true">Ano</option>
                          </select>
                        ) : f.type === "textarea" ? (
                          <textarea
                            id={f.key}
                            value={values[f.key] ?? ""}
                            onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            placeholder={f.placeholder}
                            rows={2}
                            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                          />
                        ) : (
                          <Input
                            id={f.key}
                            type={f.type === "number" ? "number" : f.type}
                            value={values[f.key] ?? ""}
                            onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            placeholder={f.placeholder}
                          />
                        )}

                        {f.hint && (
                          <p className="text-xs text-gray-500">{f.hint}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}

            {error && (
              <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                <AlertTriangle className="h-4 w-4 inline mr-2" />
                {error}
              </div>
            )}

            <div className="flex items-center justify-between sticky bottom-0 bg-white border-t border-gray-200 -mx-6 px-6 py-3">
              <span className="text-xs text-gray-500">
                {savedAt
                  ? `Uloženo v ${savedAt}`
                  : isDirty
                    ? `Změněno ${dirtyKeys.length} ${dirtyKeys.length === 1 ? "pole" : "polí"}`
                    : "Žádné změny"}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReset}
                  disabled={!isDirty || saveMutation.isPending}
                >
                  <RotateCcw className="h-3.5 w-3.5 mr-1" /> Zahodit
                </Button>
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={!isDirty || saveMutation.isPending}
                  loading={saveMutation.isPending}
                >
                  <Save className="h-3.5 w-3.5 mr-1" /> Uložit změny
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
