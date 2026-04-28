"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertTriangle, Plus, Pencil, FileText, CheckCircle, ListTodo, Trash2, PenLine,
} from "lucide-react";
import { MultiSignerPanel } from "@/components/signature/multi-signer-panel";
import { api, ApiError } from "@/lib/api";
import { useTableSort } from "@/lib/use-table-sort";
import { SortableHeader } from "@/components/ui/sortable-header";
import type { AccidentReport, Employee, Workplace, BodyPartCode } from "@/types/api";
import { BODY_PARTS } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AccidentDetailPanel } from "./accident-detail-panel";

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

// ── Schéma formuláře (zrcadlí AccidentReportCreateRequest) ───────────────────

const witnessSchema = z.object({
  name: z.string().min(1, "Jméno svědka je povinné").max(255),
  // Pokud null/empty, svědek je externí (digi podpis nelze).
  // Pokud nastaven, jde o interního zaměstnance.
  employee_id: z.string().uuid().or(z.literal("")).optional().nullable(),
  signed_at: z.string().optional().nullable(),
});

const schema = z.object({
  // Zaměstnanec
  employee_id:           z.string().uuid().or(z.literal("")).optional(),
  employee_name:         z.string().min(1, "Jméno zraněného je povinné").max(255),
  // Pracoviště — dropdown z workplaces tenantu, nebo prázdný řetězec pro
  // "Místo úrazu mimo provozovnu" (workplace_external_description nutný).
  workplace_id:          z.string().uuid().or(z.literal("")).optional(),
  workplace_external_description: z.string().max(2000).optional(),

  // Čas
  accident_date:         z.string().min(1, "Datum úrazu je povinné"),
  accident_time:         z.string().min(1, "Čas úrazu je povinný"),
  shift_start_time:      z.string().optional(),

  // Charakter zranění
  injury_type:           z.string().min(1, "Druh zranění je povinný").max(255),
  injured_body_part_code: z.enum(["A","B","C","D","E","F","G","H","I","J","K","L","M","N"], {
    required_error: "Vyber část těla dle OOPP gridu",
  }),
  injured_body_part:     z.string().min(1, "Detail zranění je povinný").max(255),
  injury_source:         z.string().min(1, "Zdroj zranění je povinný").max(255),
  injury_cause:          z.string().min(1, "Příčina úrazu je povinná"),
  injured_count:         z.coerce.number().int().min(1, "Minimálně 1").default(1),
  is_fatal:              z.boolean().default(false),
  has_other_injuries:    z.boolean().default(false),

  // Popis
  description:           z.string().min(1, "Popis úrazu je povinný"),

  // Krevní patogeny
  blood_pathogen_exposure: z.boolean().default(false),
  blood_pathogen_persons:  z.string().optional(),

  // Předpisy
  violated_regulations:    z.string().optional(),

  // Testy
  alcohol_test_performed: z.boolean().default(false),
  alcohol_test_result:    z.enum(["negative", "positive"]).nullable().optional(),
  alcohol_test_value:     z.union([
    z.coerce.number().min(0).max(99),
    z.literal(""),
  ]).optional(),
  drug_test_performed:    z.boolean().default(false),
  drug_test_result:       z.enum(["negative", "positive"]).nullable().optional(),

  // Podpisy
  injured_signed_at:      z.string().optional(),
  // True = postižený je externí (brigádník bez evidence) → digi podpis nelze.
  injured_external:       z.boolean().default(false),
  witnesses:              z.array(witnessSchema).default([]),
  supervisor_name:        z.string().max(255).optional(),
  // Vedoucí pracovník z evidence (jen z role lead_worker). Pokud None ale
  // supervisor_name vyplněn → externí vedoucí (digi podpis nelze).
  supervisor_employee_id: z.string().uuid().or(z.literal("")).optional().nullable(),
  supervisor_signed_at:   z.string().optional(),
});

type FormData = z.infer<typeof schema>;

// ── Formulář ─────────────────────────────────────────────────────────────────

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
const TEXTAREA_CLS = "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none";

function AccidentForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  employees,
  leadWorkers,
  workplaces,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  employees: Employee[];
  /** Filtrované jen na User.role='lead_worker' — pro supervisor dropdown. */
  leadWorkers: Employee[];
  /** Pracoviště v tenantu — pro výběr v poli "Pracoviště". */
  workplaces: Workplace[];
}) {
  const {
    register, handleSubmit, control, watch, setValue,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues ?? {
      injured_count: 1,
      is_fatal: false,
      has_other_injuries: false,
      blood_pathogen_exposure: false,
      alcohol_test_performed: false,
      drug_test_performed: false,
      injured_external: false,
      witnesses: [],
      supervisor_employee_id: "",
    },
  });

  const injuredExternal = watch("injured_external");
  const supervisorEmpId = watch("supervisor_employee_id");

  const { fields, append, remove } = useFieldArray({ control, name: "witnesses" });

  const alcoholOn = watch("alcohol_test_performed");
  const alcoholResult = watch("alcohol_test_result");
  const drugOn = watch("drug_test_performed");
  const bloodOn = watch("blood_pathogen_exposure");

  function handleEmployeeChange(value: string) {
    setValue("employee_id", value);
    if (value) {
      const e = employees.find(emp => emp.id === value);
      if (e) {
        setValue("employee_name", `${e.first_name} ${e.last_name}`.trim());
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      {/* — Zraněný — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Zraněný zaměstnanec</legend>

        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
          <input
            type="checkbox"
            {...register("injured_external")}
            className="h-4 w-4"
            onChange={(e) => {
              setValue("injured_external", e.target.checked);
              if (e.target.checked) setValue("employee_id", "");
            }}
          />
          Externí pracovník (brigádník, řidič dodavatele apod. — bez evidence
          v zaměstnancích; digitální podpis nebude možný)
        </label>

        {!injuredExternal && (
          <div className="space-y-1.5">
            <Label htmlFor="employee_id">Zaměstnanec * <span className="text-xs text-gray-500">(z evidence)</span></Label>
            <Controller
              name="employee_id"
              control={control}
              render={({ field }) => (
                <SearchableSelect
                  id="employee_id"
                  placeholder="— vyber zaměstnance —"
                  value={field.value || null}
                  onChange={(v) => handleEmployeeChange(v ?? "")}
                  options={employees.map((e) => ({
                    value: e.id,
                    label: `${e.last_name} ${e.first_name}`,
                    hint: e.personal_number || undefined,
                  }))}
                />
              )}
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="employee_name">Jméno zraněného *</Label>
            <Input
              id="employee_name"
              {...register("employee_name")}
              placeholder={injuredExternal ? "např. Jan Novák (externí)" : ""}
            />
            {errors.employee_name && <p className="text-xs text-red-600">{errors.employee_name.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="workplace_id">Pracoviště *</Label>
            <select
              id="workplace_id"
              {...register("workplace_id")}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— Místo úrazu mimo provozovnu —</option>
              {workplaces.map((wp) => (
                <option key={wp.id} value={wp.id}>
                  {wp.name}
                </option>
              ))}
            </select>
            {errors.workplace_id && (
              <p className="text-xs text-red-600">{errors.workplace_id.message}</p>
            )}
            {!watch("workplace_id") && (
              <div className="mt-2">
                <Label htmlFor="workplace_external_description" className="text-xs">
                  Popis místa úrazu (mimo provozovnu) *
                </Label>
                <textarea
                  id="workplace_external_description"
                  rows={2}
                  placeholder="např. Stavba Olomouc, ul. Wolkerova 5, lešení 3. patro"
                  {...register("workplace_external_description")}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
          </div>
        </div>
      </fieldset>

      {/* — Čas — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Čas úrazu</legend>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="accident_date">Datum úrazu *</Label>
            <Input id="accident_date" type="date" {...register("accident_date")} />
            {errors.accident_date && <p className="text-xs text-red-600">{errors.accident_date.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="accident_time">Čas úrazu *</Label>
            <Input id="accident_time" type="time" {...register("accident_time")} />
            {errors.accident_time && <p className="text-xs text-red-600">{errors.accident_time.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="shift_start_time">Začátek směny</Label>
            <Input id="shift_start_time" type="time" {...register("shift_start_time")} />
          </div>
        </div>
      </fieldset>

      {/* — Charakter zranění — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Charakter zranění</legend>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="injury_type">Druh zranění *</Label>
            <Input id="injury_type" placeholder="např. řezná rána, zlomenina" {...register("injury_type")} />
            {errors.injury_type && <p className="text-xs text-red-600">{errors.injury_type.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="injured_body_part_code">Část těla (OOPP) *</Label>
            <select
              id="injured_body_part_code"
              {...register("injured_body_part_code")}
              className="block w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            >
              <option value="">— vyber —</option>
              {BODY_PARTS.map((bp) => (
                <option key={bp.code} value={bp.code}>
                  {bp.code}. {bp.label}{bp.group ? ` (${bp.group})` : ""}
                </option>
              ))}
            </select>
            {errors.injured_body_part_code && (
              <p className="text-xs text-red-600">{errors.injured_body_part_code.message}</p>
            )}
            <p className="text-xs text-gray-500">
              Standardizovaný kód dle NV 390/2021 — automaticky propojí úraz s OOPP gridem.
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="injured_body_part">Detail zranění *</Label>
          <Input
            id="injured_body_part"
            placeholder="např. levá ruka — prst, dorzální strana"
            {...register("injured_body_part")}
          />
          {errors.injured_body_part && (
            <p className="text-xs text-red-600">{errors.injured_body_part.message}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="injury_source">Zdroj zranění *</Label>
          <Input id="injury_source" placeholder="např. ostrý nástroj, padající předmět" {...register("injury_source")} />
          {errors.injury_source && <p className="text-xs text-red-600">{errors.injury_source.message}</p>}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="injury_cause">Příčina úrazu *</Label>
          <textarea id="injury_cause" rows={2} {...register("injury_cause")} className={TEXTAREA_CLS} />
          {errors.injury_cause && <p className="text-xs text-red-600">{errors.injury_cause.message}</p>}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="injured_count">Počet zraněných *</Label>
            <Input id="injured_count" type="number" min="1" {...register("injured_count")} />
            {errors.injured_count && <p className="text-xs text-red-600">{errors.injured_count.message}</p>}
          </div>
          <label className="flex items-end gap-2 pb-2 cursor-pointer">
            <input type="checkbox" {...register("is_fatal")} className="rounded" />
            <span className="text-sm font-medium">Smrtelný úraz</span>
          </label>
          <label className="flex items-end gap-2 pb-2 cursor-pointer">
            <input type="checkbox" {...register("has_other_injuries")} className="rounded" />
            <span className="text-sm font-medium">Více zranění (těžké)</span>
          </label>
        </div>
      </fieldset>

      {/* — Popis — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Popis úrazu</legend>
        <div className="space-y-1.5">
          <Label htmlFor="description">Detailní popis *</Label>
          <textarea
            id="description"
            rows={4}
            placeholder="Přesný popis okolností, jak k úrazu došlo (čas, místo, činnost, mechanismus zranění)…"
            {...register("description")}
            className={TEXTAREA_CLS}
          />
          {errors.description && <p className="text-xs text-red-600">{errors.description.message}</p>}
        </div>
      </fieldset>

      {/* — Krevní patogeny — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Expozice krevním patogenům</legend>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" {...register("blood_pathogen_exposure")} className="rounded" />
          <span className="text-sm font-medium">Došlo k expozici krevním patogenům</span>
        </label>
        {bloodOn && (
          <div className="space-y-1.5">
            <Label htmlFor="blood_pathogen_persons">Dotčené osoby (jména, role)</Label>
            <textarea id="blood_pathogen_persons" rows={2} {...register("blood_pathogen_persons")} className={TEXTAREA_CLS} />
          </div>
        )}
      </fieldset>

      {/* — Porušené předpisy — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Porušené předpisy</legend>
        <div className="space-y-1.5">
          <Label htmlFor="violated_regulations">Které právní/interní předpisy byly porušeny</Label>
          <textarea
            id="violated_regulations"
            rows={2}
            placeholder="např. § 102 ZP, vnitřní předpis č. ...; pokud žádné, nechte prázdné"
            {...register("violated_regulations")}
            className={TEXTAREA_CLS}
          />
        </div>
      </fieldset>

      {/* — Testy — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Testy na alkohol a omamné látky</legend>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" {...register("alcohol_test_performed")} className="rounded" />
              <span className="text-sm font-medium">Test alkoholu proveden</span>
            </label>
            {alcoholOn && (
              <select {...register("alcohol_test_result")} className={SELECT_CLS}>
                <option value="">— Vyberte výsledek —</option>
                <option value="negative">Negativní</option>
                <option value="positive">Pozitivní</option>
              </select>
            )}
            {alcoholOn && alcoholResult === "positive" && (
              <div className="space-y-1.5">
                <Label htmlFor="alcohol_test_value" className="text-xs">Naměřená hodnota (promile) *</Label>
                <Input
                  id="alcohol_test_value"
                  type="number"
                  step="0.01"
                  min="0"
                  max="99"
                  placeholder="např. 0,45"
                  {...register("alcohol_test_value")}
                />
                {errors.alcohol_test_value && (
                  <p className="text-xs text-red-600">{errors.alcohol_test_value.message as string}</p>
                )}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" {...register("drug_test_performed")} className="rounded" />
              <span className="text-sm font-medium">Test omamných látek proveden</span>
            </label>
            {drugOn && (
              <select {...register("drug_test_result")} className={SELECT_CLS}>
                <option value="">— Vyberte výsledek —</option>
                <option value="negative">Negativní</option>
                <option value="positive">Pozitivní</option>
              </select>
            )}
          </div>
        </div>
      </fieldset>

      {/* — Podpisy — */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-700 mb-1">Podpisy</legend>

        <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 px-3 py-2 text-xs text-blue-800 dark:text-blue-200">
          Datum podpisu se vyplňuje automaticky při digitálním podpisu zraněného,
          vedoucího a svědků. Pro externího zraněného (mimo evidenci) podpis
          probíhá fyzickým tiskem a datum se nezadává.
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Svědci</Label>
            <Button
              type="button" size="sm" variant="outline"
              onClick={() => append({ name: "", employee_id: "", signed_at: null })}
            >
              <Plus className="h-3 w-3 mr-1" /> Přidat svědka
            </Button>
          </div>
          {fields.length === 0 && (
            <p className="text-xs text-gray-400 italic">Žádný svědek</p>
          )}
          {fields.map((field, idx) => (
            <div key={field.id} className="rounded-md border border-gray-200 dark:border-gray-700 p-2 space-y-2">
              <div className="space-y-1">
                <Label className="text-xs">Svědek (z evidence) — pokud externí, nech prázdné</Label>
                <Controller
                  name={`witnesses.${idx}.employee_id` as const}
                  control={control}
                  render={({ field: f }) => (
                    <SearchableSelect
                      placeholder="— Externí svědek (zadej jméno níže) —"
                      value={(f.value as string) || null}
                      onChange={(v) => {
                        f.onChange(v ?? "");
                        // Pokud zaměstnanec, autodoplň jméno
                        if (v) {
                          const e = employees.find((emp) => emp.id === v);
                          if (e) {
                            setValue(
                              `witnesses.${idx}.name` as const,
                              `${e.first_name} ${e.last_name}`.trim(),
                            );
                          }
                        }
                      }}
                      options={employees.map((e) => ({
                        value: e.id,
                        label: `${e.last_name} ${e.first_name}`,
                      }))}
                    />
                  )}
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label htmlFor={`witness-${idx}-name`} className="text-xs">Jméno svědka *</Label>
                  <Input id={`witness-${idx}-name`} {...register(`witnesses.${idx}.name`)} />
                  {errors.witnesses?.[idx]?.name && (
                    <p className="text-xs text-red-600">{errors.witnesses[idx]?.name?.message}</p>
                  )}
                </div>
                <div className="w-40 space-y-1">
                  <Label htmlFor={`witness-${idx}-date`} className="text-xs">Datum podpisu</Label>
                  <Input id={`witness-${idx}-date`} type="date" {...register(`witnesses.${idx}.signed_at`)} />
                </div>
                <button
                  type="button"
                  onClick={() => remove(idx)}
                  className="rounded p-2 text-gray-400 hover:text-red-600 hover:bg-red-50"
                  title="Odebrat"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-2 rounded-md border border-gray-200 dark:border-gray-700 p-2">
          <div className="space-y-1">
            <Label htmlFor="supervisor_employee_id" className="text-xs">
              Vedoucí pracovník (jen role &bdquo;lead_worker&ldquo;) — pokud externí, nech prázdné
            </Label>
            <Controller
              name="supervisor_employee_id"
              control={control}
              render={({ field }) => (
                <SearchableSelect
                  id="supervisor_employee_id"
                  placeholder="— Externí vedoucí (zadej jméno níže) —"
                  value={(field.value as string) || null}
                  onChange={(v) => {
                    field.onChange(v ?? "");
                    if (v) {
                      const e = leadWorkers.find((emp) => emp.id === v);
                      if (e) {
                        setValue("supervisor_name", `${e.first_name} ${e.last_name}`.trim());
                      }
                    }
                  }}
                  options={leadWorkers.map((e) => ({
                    value: e.id,
                    label: `${e.last_name} ${e.first_name}`,
                  }))}
                />
              )}
            />
            {leadWorkers.length === 0 && (
              <p className="text-xs text-amber-600">
                Žádný zaměstnanec nemá roli &bdquo;vedoucí pracovník&ldquo;. Pokud chceš
                interního vedoucího, nastav mu roli v modulu Zaměstnanci.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="supervisor_name" className="text-xs">Jméno vedoucího</Label>
            <Input id="supervisor_name" {...register("supervisor_name")} />
            <p className="text-xs text-gray-500">
              Datum podpisu vedoucího se vyplní automaticky při digitálním podpisu.
            </p>
          </div>
        </div>

        {/* Indikátor digitálního podpisu */}
        {(injuredExternal
          || (fields.length > 0 && fields.some((_, idx) => !watch(`witnesses.${idx}.employee_id` as const)))
          || (watch("supervisor_name") && !supervisorEmpId)) ? (
          <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
            ⚠ Některý z účastníků je <strong>externí</strong> — digitální podpis nebude
            možný. Po finalizaci je nutné formulář vytisknout a fyzicky podepsat.
          </div>
        ) : (
          <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-300 dark:border-emerald-700 px-3 py-2 text-xs text-emerald-800 dark:text-emerald-200">
            ✓ Všichni účastníci jsou interní zaměstnanci — po finalizaci bude
            možný <strong>digitální podpis</strong> přes heslo nebo SMS kód.
          </div>
        )}
      </fieldset>

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

// ── Helpery pro převod (date, time → ISO řetězce; čisté null) ────────────────

function cleanFormData(data: FormData): Record<string, unknown> {
  // Empty stringy → null pro volitelné pole
  const clean: Record<string, unknown> = { ...data };
  const optionalFields = [
    "employee_id", "shift_start_time", "blood_pathogen_persons",
    "violated_regulations", "supervisor_name", "supervisor_employee_id",
    "supervisor_signed_at",
    "injured_signed_at", "alcohol_test_result", "alcohol_test_value", "drug_test_result",
    "workplace_id", "workplace_external_description", "workplace",
  ];
  for (const f of optionalFields) {
    if (clean[f] === "" || clean[f] === undefined) clean[f] = null;
  }
  // Pokud test neproveden, vyresetuj výsledek a hodnotu
  if (!clean.alcohol_test_performed) {
    clean.alcohol_test_result = null;
    clean.alcohol_test_value = null;
  }
  // Promile jen u positive
  if (clean.alcohol_test_result !== "positive") clean.alcohol_test_value = null;
  if (!clean.drug_test_performed) clean.drug_test_result = null;
  if (!clean.blood_pathogen_exposure) clean.blood_pathogen_persons = null;
  // Witness signed_at "" → null, employee_id "" → null
  if (Array.isArray(clean.witnesses)) {
    clean.witnesses = (
      clean.witnesses as { name: string; employee_id?: string | null; signed_at: string | null }[]
    ).map((w) => ({
      name: w.name,
      employee_id: w.employee_id || null,
      signed_at: w.signed_at === "" ? null : w.signed_at,
    }));
  }
  // Pokud postižený = externí, employee_id musí být null
  if (clean.injured_external) {
    clean.employee_id = null;
  }
  return clean;
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function AccidentReportsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("draft");
  const [signedFilter, setSignedFilter] = useState<"" | "signed" | "unsigned">("");
  const [editReport, setEditReport] = useState<AccidentReport | null>(null);
  const [detailReport, setDetailReport] = useState<AccidentReport | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [signingReport, setSigningReport] = useState<AccidentReport | null>(null);

  const { data: reportsRaw = [], isLoading } = useQuery<AccidentReport[]>({
    queryKey: ["accident-reports", statusFilter, signedFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("report_status", statusFilter);
      if (signedFilter) params.set("signed", signedFilter);
      const qs = params.toString();
      return api.get(`/accident-reports${qs ? `?${qs}` : ""}`);
    },
  });
  // Všechny záznamy (bez filtrů) — pro výpočet počtů u filter chips.
  const { data: reportsAll = [] } = useQuery<AccidentReport[]>({
    queryKey: ["accident-reports", "all"],
    queryFn: () => api.get("/accident-reports"),
    staleTime: 60_000,
  });
  const statusCounts = useMemo(() => ({
    all: reportsAll.length,
    draft: reportsAll.filter((r) => r.status === "draft").length,
    final: reportsAll.filter((r) => r.status === "final").length,
    archived: reportsAll.filter((r) => r.status === "archived").length,
  }), [reportsAll]);
  const signedCounts = useMemo(() => ({
    all: reportsAll.length,
    signed: reportsAll.filter((r) => r.is_fully_signed).length,
    unsigned: reportsAll.filter(
      (r) => r.signature_required && !r.is_fully_signed,
    ).length,
  }), [reportsAll]);
  const {
    sortedItems: reports,
    sortKey, sortDir, toggleSort,
  } = useTableSort<AccidentReport>(reportsRaw, "accident_date", "desc");

  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => api.get("/employees?emp_status=active"),
    staleTime: 5 * 60 * 1000,
  });
  // Vedoucí pracovníci — jen User.role='lead_worker'. Pro filtr v dropdownu
  // "Vedoucí pracovník (z evidence)".
  const { data: leadWorkers = [] } = useQuery<Employee[]>({
    queryKey: ["employees", "lead-workers"],
    queryFn: () => api.get("/employees?emp_status=active&user_role=lead_worker"),
    staleTime: 5 * 60 * 1000,
  });
  // Workplaces pro dropdown "Pracoviště" (s plant_name pro hierarchii).
  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces", "active"],
    queryFn: () => api.get("/workplaces?wp_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    mutationFn: (data: FormData) => api.post("/accident-reports", cleanFormData(data)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-reports"] });
      setCreateOpen(false);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FormData }) =>
      api.patch(`/accident-reports/${id}`, cleanFormData(data)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accident-reports"] });
      setEditReport(null);
    },
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
        title="Pracovní úrazy"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Nová nehoda
          </Button>
        }
      />

      <div className="p-6 space-y-4">
        {/* Filtry */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1 w-16">Stav:</span>
            {([
              { val: "",         label: "Všechny",     count: statusCounts.all },
              { val: "draft",    label: "Rozpracované", count: statusCounts.draft },
              { val: "final",    label: "Finální",     count: statusCounts.final },
              { val: "archived", label: "Archivované", count: statusCounts.archived },
            ] as const).map(({ val, label, count }) => (
              <button
                key={val}
                onClick={() => setStatusFilter(val)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  statusFilter === val
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
                )}
              >
                {label} ({count})
              </button>
            ))}
            <span className="ml-auto text-xs text-gray-400">{reports.length} zobrazeno</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1 w-16">Podpis:</span>
            {([
              { val: "", label: "Vše", count: signedCounts.all },
              { val: "signed", label: "Podepsané", count: signedCounts.signed },
              { val: "unsigned", label: "Nepodepsané", count: signedCounts.unsigned },
            ] as const).map(({ val, label, count }) => (
              <button
                key={val}
                onClick={() => setSignedFilter(val)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  signedFilter === val
                    ? "bg-emerald-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
                )}
              >
                {label} ({count})
              </button>
            ))}
          </div>
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
                <p className="text-sm">Žádné záznamy</p>
                <p className="text-xs mt-1">Přidejte záznam o nehodě tlačítkem výše</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <SortableHeader sortKey="accident_date" current={sortKey} dir={sortDir} onSort={toggleSort}>Datum</SortableHeader>
                      <SortableHeader sortKey="employee_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Zraněný</SortableHeader>
                      <SortableHeader sortKey="workplace" current={sortKey} dir={sortDir} onSort={toggleSort}>Pracoviště</SortableHeader>
                      <SortableHeader sortKey="injury_type" current={sortKey} dir={sortDir} onSort={toggleSort}>Druh zranění</SortableHeader>
                      <SortableHeader sortKey="status" current={sortKey} dir={sortDir} onSort={toggleSort}>Stav</SortableHeader>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {reports.map(report => (
                      <tr key={report.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 text-gray-600">{formatDate(report.accident_date)}</td>
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {report.employee_name}
                          {report.is_fatal && (
                            <span className="ml-2 inline-flex rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-[10px] font-semibold">
                              SMRTELNÝ
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-gray-600">{report.workplace}</td>
                        <td className="py-3 px-4 text-gray-600">
                          <div>{report.injury_type}</div>
                          <div className="text-xs text-gray-400">{report.injured_body_part}</div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5">
                            <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[report.status])}>
                              {STATUS_LABELS[report.status]}
                            </span>
                            {/* Indikátor podpisu */}
                            {!report.signature_required ? (
                              <span
                                className="rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-2 py-0.5 text-[10px] font-medium"
                                title="Některý z účastníků je externí — vyžaduje fyzický podpis"
                              >
                                Fyz. podpis
                              </span>
                            ) : report.is_fully_signed ? (
                              <span
                                className="rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-medium"
                                title="Všechny strany podepsaly digitálně"
                              >
                                ✓ Podepsáno
                              </span>
                            ) : report.required_signer_employee_ids.length > 0 ? (
                              <span
                                className="rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 text-[10px] font-medium"
                                title="Čeká se na podpisy"
                              >
                                {report.signed_count}/{report.required_signer_employee_ids.length} podpisů
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-1">
                            {report.status === "draft" && (
                              <Tooltip label="Upravit záznam">
                                <button
                                  onClick={() => { setServerError(null); setEditReport(report); }}
                                  className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                  aria-label="Upravit záznam"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>
                            )}
                            <Tooltip label="Akční plán, fotky a podepsaný dokument">
                              <button
                                onClick={() => setDetailReport(report)}
                                className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                aria-label="Detail"
                              >
                                <ListTodo className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
                            <Tooltip label="Stáhnout PDF záznamu">
                              <button
                                onClick={() => window.open(`/api/v1/accident-reports/${report.id}/pdf`, "_blank")}
                                className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                                aria-label="Stáhnout PDF"
                              >
                                <FileText className="h-3.5 w-3.5" />
                              </button>
                            </Tooltip>
                            {report.status === "final"
                              && report.signature_required
                              && !report.is_fully_signed && (
                              <Tooltip label="Digitální podpisy účastníků">
                                <button
                                  onClick={() => setSigningReport(report)}
                                  className="rounded p-1 text-blue-600 hover:bg-blue-50 transition-colors"
                                  aria-label="Podepsat"
                                >
                                  <PenLine className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>
                            )}
                            {report.status === "draft" && (
                              <Tooltip label="Finalizovat (uzamknout úpravy)">
                                <button
                                  onClick={() => {
                                    if (confirm("Finalizovat tento záznam? Po finalizaci ho nelze upravovat."))
                                      finalizeMutation.mutate(report.id);
                                  }}
                                  className="rounded p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                                  aria-label="Finalizovat"
                                >
                                  <CheckCircle className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>
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

      {/* Multi-signer panel pro digitální podpis úrazu */}
      {signingReport && (
        <MultiSignerPanel
          open={!!signingReport}
          onClose={() => setSigningReport(null)}
          docType="accident_report"
          docId={signingReport.id}
          title={`Podpisy: ${signingReport.employee_name} — ${formatDate(signingReport.accident_date)}`}
          onCompleted={() => {
            qc.invalidateQueries({ queryKey: ["accident-reports"] });
          }}
        />
      )}

      {/* Dialog: Nová nehoda */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nový záznam o pracovním úrazu"
        size="lg"
      >
        <AccidentForm
          onSubmit={(data) => { setServerError(null); createMutation.mutate(data); }}
          isSubmitting={createMutation.isPending}
          serverError={serverError}
          employees={employees}
          leadWorkers={leadWorkers}
          workplaces={workplaces}
        />
      </Dialog>

      {/* Dialog: Upravit nehodu */}
      <Dialog
        open={!!editReport}
        onClose={() => setEditReport(null)}
        title={editReport ? `Úprava: ${editReport.employee_name} — ${formatDate(editReport.accident_date)}` : ""}
        size="lg"
      >
        {editReport && (
          <AccidentForm
            defaultValues={{
              employee_id:             editReport.employee_id ?? "",
              employee_name:           editReport.employee_name,
              workplace_id:            editReport.workplace_id ?? "",
              workplace_external_description: editReport.workplace_external_description ?? "",
              accident_date:           editReport.accident_date,
              accident_time:           editReport.accident_time?.slice(0, 5) ?? "",
              shift_start_time:        editReport.shift_start_time?.slice(0, 5) ?? "",
              injury_type:             editReport.injury_type,
              injured_body_part_code:  (editReport.injured_body_part_code ?? "") as BodyPartCode,
              injured_body_part:       editReport.injured_body_part,
              injury_source:           editReport.injury_source,
              injury_cause:            editReport.injury_cause,
              injured_count:           editReport.injured_count,
              is_fatal:                editReport.is_fatal,
              has_other_injuries:      editReport.has_other_injuries,
              description:             editReport.description,
              blood_pathogen_exposure: editReport.blood_pathogen_exposure,
              blood_pathogen_persons:  editReport.blood_pathogen_persons ?? "",
              violated_regulations:    editReport.violated_regulations ?? "",
              alcohol_test_performed:  editReport.alcohol_test_performed,
              alcohol_test_result:     editReport.alcohol_test_result,
              alcohol_test_value:      editReport.alcohol_test_value === null
                ? ""
                : (typeof editReport.alcohol_test_value === "number"
                    ? editReport.alcohol_test_value
                    : Number(editReport.alcohol_test_value)),
              drug_test_performed:     editReport.drug_test_performed,
              drug_test_result:        editReport.drug_test_result,
              injured_signed_at:       editReport.injured_signed_at ?? "",
              injured_external:        editReport.injured_external ?? false,
              witnesses:               (editReport.witnesses ?? []).map((w) => ({
                name: w.name,
                employee_id: w.employee_id ?? "",
                signed_at: w.signed_at ?? "",
              })),
              supervisor_name:         editReport.supervisor_name ?? "",
              supervisor_employee_id:  editReport.supervisor_employee_id ?? "",
              supervisor_signed_at:    editReport.supervisor_signed_at ?? "",
            }}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editReport.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            employees={employees}
            leadWorkers={leadWorkers}
            workplaces={workplaces}
          />
        )}
      </Dialog>

      {/* Dialog: Akční plán + fotky */}
      <Dialog
        open={!!detailReport}
        onClose={() => setDetailReport(null)}
        title={detailReport ? `${detailReport.employee_name} — akční plán a fotodokumentace` : ""}
        size="lg"
      >
        {detailReport && (
          <AccidentDetailPanel
            accidentId={detailReport.id}
            reportStatus={detailReport.status}
          />
        )}
      </Dialog>
    </div>
  );
}
