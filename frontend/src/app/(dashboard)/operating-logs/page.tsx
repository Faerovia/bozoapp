"use client";

/**
 * Modul Provozní deníky.
 *
 * Layout 2-pane:
 *  - Levý panel: list zařízení (filter podle kategorie a plant)
 *  - Pravý panel: detail zařízení + tabulka záznamů + tlačítko nový zápis
 */

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import {
  Plus, Pencil, Trash2, BookOpenCheck, ClipboardList, Info,
  CheckCircle2, XCircle, ArrowUp, ArrowDown, QrCode, AlertTriangle, Copy,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  DeviceCategory, OperatingLogDevice, OperatingLogEntry, OperatingPeriod, Plant,
} from "@/types/api";
import {
  DEVICE_CATEGORY_LABELS,
  DEVICE_CATEGORY_PERIODICITY_INFO,
  OPERATING_PERIOD_LABELS,
} from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { cn } from "@/lib/utils";

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

const CATEGORY_OPTIONS: { value: DeviceCategory; label: string }[] =
  (Object.entries(DEVICE_CATEGORY_LABELS) as [DeviceCategory, string][])
    .map(([value, label]) => ({ value, label }));

const PERIOD_OPTIONS: { value: OperatingPeriod; label: string }[] =
  (Object.entries(OPERATING_PERIOD_LABELS) as [OperatingPeriod, string][])
    .map(([value, label]) => ({ value, label }));

// ── Tlačítko + dialog: převzít kontrolní úkony z jiného zařízení ───────────
//
// Při zakládání nebo úpravě zařízení (typicky stejné kategorie — např.
// Vysokozdvižný vozík) si OZO/HR může vybrat jiné existující zařízení a
// zkopírovat z něj `check_items`. Šetří čas a sjednocuje úkony napříč
// stejnými typy zařízení (vyhláška + interní směrnice typicky vyžadují
// totéž).
//
// Filter: podle aktuálně vybrané kategorie (selectedCategory). Klient může
// zatrhnout přepínač pro „všechna zařízení" pokud chce úkony z jiné kategorie.

function CopyItemsFromDevice({
  category,
  onPick,
}: {
  category: DeviceCategory;
  onPick: (items: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [allCategories, setAllCategories] = useState(false);

  const { data: devices = [] } = useQuery<OperatingLogDevice[]>({
    queryKey: ["operating-logs", "devices-all", allCategories ? "all" : category],
    queryFn: () => {
      const qs = new URLSearchParams({ device_status: "active" });
      if (!allCategories && category) qs.set("category", category);
      return api.get(`/operating-logs/devices?${qs.toString()}`);
    },
    enabled: open,
  });

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        title="Zkopíruje úkony z existujícího zařízení (přepíše stávající)"
      >
        <Copy className="h-3.5 w-3.5 mr-1" /> Převzít z jiného zařízení
      </Button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Převzít kontrolní úkony"
        description={
          allCategories
            ? "Všechna aktivní zařízení v tenantu"
            : `Aktivní zařízení kategorie „${DEVICE_CATEGORY_LABELS[category] ?? category}"`
        }
        size="md"
      >
        <div className="space-y-3">
          <Label className="flex items-center gap-2 cursor-pointer text-xs">
            <input
              type="checkbox"
              checked={allCategories}
              onChange={(e) => setAllCategories(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span>Zobrazit zařízení všech kategorií</span>
          </Label>

          {devices.length === 0 ? (
            <div className="rounded-md bg-gray-50 dark:bg-gray-800 p-4 text-center text-sm text-gray-500">
              Žádná jiná zařízení této kategorie zatím neexistují.
            </div>
          ) : (
            <div className="max-h-80 overflow-auto divide-y divide-gray-100 dark:divide-gray-700 rounded-md border border-gray-200 dark:border-gray-700">
              {devices.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => {
                    onPick(d.check_items ?? []);
                    setOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                        {d.title}
                        {d.device_code && (
                          <span className="ml-1 text-xs text-gray-400">
                            ({d.device_code})
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {DEVICE_CATEGORY_LABELS[d.category as DeviceCategory] ?? d.category}
                        {" · "}
                        {(d.check_items?.length ?? 0)} úkonů
                      </div>
                    </div>
                    <Copy className="h-4 w-4 text-gray-300 shrink-0" />
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </Dialog>
    </>
  );
}


// ── Form: zařízení (1-20 kontrolních úkonů) ────────────────────────────────

interface DeviceFormData {
  category: DeviceCategory;
  title: string;
  device_code: string;
  location: string;
  plant_id: string;
  period: OperatingPeriod;
  period_note: string;
  notes: string;
  check_items: { value: string }[];
  responsible_employee_id: string;
}

function DeviceForm({
  defaultValues, plants, onSubmit, isSubmitting, serverError,
}: {
  defaultValues?: Partial<DeviceFormData>;
  plants: Plant[];
  onSubmit: (d: DeviceFormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const { register, handleSubmit, watch, control, setValue } = useForm<DeviceFormData>({
    defaultValues: {
      category: defaultValues?.category ?? "vzv",
      title: defaultValues?.title ?? "",
      device_code: defaultValues?.device_code ?? "",
      location: defaultValues?.location ?? "",
      plant_id: defaultValues?.plant_id ?? "",
      period: defaultValues?.period ?? "daily",
      period_note: defaultValues?.period_note ?? "",
      notes: defaultValues?.notes ?? "",
      check_items: defaultValues?.check_items ?? [{ value: "" }],
      responsible_employee_id: defaultValues?.responsible_employee_id ?? "",
    },
  });

  // Načti aktivní zaměstnance pro dropdown zodpovědné osoby
  const { data: employees = [] } = useQuery<Array<{
    id: string; full_name: string; email: string | null;
  }>>({
    queryKey: ["employees", "active"],
    queryFn: () => api.get("/employees?status=active"),
  });
  const responsibleEmpId = watch("responsible_employee_id");
  const { fields, append, remove, swap } = useFieldArray({
    control,
    name: "check_items",
  });
  const selectedCategory = watch("category") as DeviceCategory;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-4"
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="category">Kategorie zařízení *</Label>
          <select id="category" {...register("category")} className={SELECT_CLS}>
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="plant_id">Provozovna</Label>
          <select id="plant_id" {...register("plant_id")} className={SELECT_CLS}>
            <option value="">— bez plantu —</option>
            {plants.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="title">Označení zařízení *</Label>
        <Input id="title" {...register("title", { required: true })}
          placeholder="VZV Linde H25 / Kotel Viessmann V2" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="device_code">Výrobní č. / interní ID</Label>
          <Input id="device_code" {...register("device_code")} placeholder="VZV-001" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="location">Umístění</Label>
          <Input id="location" {...register("location")} placeholder="Hala B, sklad" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor="period">Periodicita kontrol *</Label>
            <Tooltip label={DEVICE_CATEGORY_PERIODICITY_INFO[selectedCategory]}>
              <Info className="h-3.5 w-3.5 text-blue-500 cursor-help" />
            </Tooltip>
          </div>
          <select id="period" {...register("period")} className={SELECT_CLS}>
            {PERIOD_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="period_note">Upřesnění</Label>
          <Input id="period_note" {...register("period_note")} placeholder="Před každou změnou obsluhy" />
        </div>
      </div>

      {/* Check items */}
      <div className="rounded-md border border-blue-200 bg-blue-50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <Label>Kontrolní úkony (1–20 položek) *</Label>
          <div className="flex items-center gap-2">
            <CopyItemsFromDevice
              category={selectedCategory}
              onPick={(items) => {
                // Replace existing items s úkony z vybraného zařízení.
                // Trim na 20 (limit modelu).
                const trimmed = items.slice(0, 20).map((v) => ({ value: v }));
                setValue(
                  "check_items",
                  trimmed.length > 0 ? trimmed : [{ value: "" }],
                  { shouldDirty: true },
                );
              }}
            />
            <span className="text-xs text-blue-700">{fields.length} / 20</span>
          </div>
        </div>
        {fields.map((f, i) => (
          <div key={f.id} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-6 shrink-0">{i + 1}.</span>
            <Input
              {...register(`check_items.${i}.value` as const, { required: true })}
              placeholder={`Kontrola ${i + 1}: brzdy, hydraulika, …`}
              className="flex-1"
            />
            <button
              type="button"
              onClick={() => i > 0 && swap(i, i - 1)}
              disabled={i === 0}
              className="rounded p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => i < fields.length - 1 && swap(i, i + 1)}
              disabled={i === fields.length - 1}
              className="rounded p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => fields.length > 1 && remove(i)}
              disabled={fields.length === 1}
              className="rounded p-1 text-gray-400 hover:text-red-600 disabled:opacity-30"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={fields.length >= 20}
          onClick={() => append({ value: "" })}
        >
          <Plus className="h-4 w-4 mr-1" /> Přidat úkon
        </Button>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="responsible_employee_id">
          Zodpovědná osoba (notifikace)
        </Label>
        <SearchableSelect
          options={employees.map((e) => ({
            value: e.id,
            label: e.email ? `${e.full_name} · ${e.email}` : e.full_name,
          }))}
          value={responsibleEmpId}
          onChange={(v) => setValue("responsible_employee_id", v ?? "")}
          placeholder="— bez zodpovědné osoby —"
        />
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Této osobě budou chodit emailové alerty, pokud nebudou prováděny
          zápisy v provozním deníku dle nastavené periodicity. Nemá-li
          zaměstnanec email, alerty mu nebudou doručeny.
        </p>
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
        <Button type="submit" loading={isSubmitting}>Uložit zařízení</Button>
      </div>
    </form>
  );
}

// ── Form: nový zápis (denní kontrola) ──────────────────────────────────────

interface AuthMeResponse {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
}

type Capability = "yes" | "no" | "conditional";

function EntryForm({
  device, onSubmit, isSubmitting, serverError,
}: {
  device: OperatingLogDevice;
  onSubmit: (d: {
    performed_at: string;
    performed_by_name: string;
    capable_items: Capability[];
    overall_status: Capability;
    notes: string | null;
  }) => void;
  isSubmitting: boolean;
  serverError: string | null;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [performedAt, setPerformedAt] = useState(today);
  const [performedByName, setPerformedByName] = useState("");
  const [capable, setCapable] = useState<Capability[]>(
    device.check_items.map(() => "yes" as Capability),
  );
  const [overall, setOverall] = useState<Capability>("yes");
  const [notes, setNotes] = useState("");

  // Auto-fill performed_by_name z přihlášeného uživatele (full_name OR email)
  const { data: me } = useQuery<AuthMeResponse>({
    queryKey: ["auth", "me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 10 * 60 * 1000,
  });
  useEffect(() => {
    if (me && performedByName === "") {
      const auto = me.full_name?.trim() || me.email;
      if (auto) setPerformedByName(auto);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  function setItem(i: number, v: Capability) {
    setCapable((arr) => arr.map((x, idx) => (idx === i ? v : x)));
    // Auto-bumpneme overall pokud uživatel označil dílčí položku jako horší
    if (v === "no" && overall !== "no") setOverall("no");
    else if (v === "conditional" && overall === "yes") setOverall("conditional");
  }

  // Helper render pro 3-way segmented button
  const itemBtnCls = (active: boolean, color: "green" | "amber" | "red") => cn(
    "rounded-md px-2.5 py-1 text-xs font-medium border transition-colors",
    active && color === "green" && "bg-green-100 border-green-300 text-green-700",
    active && color === "amber" && "bg-amber-100 border-amber-300 text-amber-700",
    active && color === "red" && "bg-red-100 border-red-300 text-red-700",
    !active && cn(
      "bg-white border-gray-200 text-gray-400",
      color === "green" && "hover:border-green-300",
      color === "amber" && "hover:border-amber-300",
      color === "red" && "hover:border-red-300",
    ),
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          performed_at: performedAt,
          performed_by_name: performedByName,
          capable_items: capable,
          overall_status: overall,
          notes: notes || null,
        });
      }}
      className="space-y-4"
    >
      <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-900">
        ℹ Datum a jméno kontrolora se automaticky vyplnily — můžete je změnit, pokud zapisujete zpětně za jinou osobu.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="performed_at">Datum kontroly *</Label>
          <Input
            id="performed_at"
            type="date"
            value={performedAt}
            onChange={(e) => setPerformedAt(e.target.value)}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="performed_by_name">Kontroloval (jméno) *</Label>
          <Input
            id="performed_by_name"
            value={performedByName}
            onChange={(e) => setPerformedByName(e.target.value)}
            required
            placeholder="Jan Novák"
          />
        </div>
      </div>

      <div className="rounded-md border border-gray-200 p-3 space-y-2">
        <div className="flex items-center justify-between border-b border-gray-100 pb-2 mb-1">
          <Label>Kontrolní úkony</Label>
          <span className="text-xs font-medium text-gray-500 uppercase">
            Způsobilý k provozu
          </span>
        </div>
        {device.check_items.map((item, i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-1 border-b border-gray-100 last:border-b-0">
            <span className="text-sm text-gray-700 flex-1">
              <span className="text-gray-400 mr-2">{i + 1}.</span>
              {item}
            </span>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                onClick={() => setItem(i, "yes")}
                className={itemBtnCls(capable[i] === "yes", "green")}
              >
                <CheckCircle2 className="h-3.5 w-3.5 inline mr-1" />
                ANO
              </button>
              <button
                type="button"
                onClick={() => setItem(i, "conditional")}
                className={itemBtnCls(capable[i] === "conditional", "amber")}
                title="Závada, ale lze podmíněně provozovat"
              >
                <AlertTriangle className="h-3.5 w-3.5 inline mr-1" />
                Podmíněný
              </button>
              <button
                type="button"
                onClick={() => setItem(i, "no")}
                className={itemBtnCls(capable[i] === "no", "red")}
              >
                <XCircle className="h-3.5 w-3.5 inline mr-1" />
                NE
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-amber-900">Souhrnná způsobilost k provozu</p>
            <p className="text-xs text-amber-700 leading-snug mt-0.5">
              <strong>ANO</strong> = bez závad · <strong>Podmíněný</strong> = drobná závada,
              lze provozovat se zvýšenou opatrností (pošle alert) ·
              <strong> NE</strong> = vyřadit z provozu (pošle alert)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-3">
          <button
            type="button"
            onClick={() => setOverall("yes")}
            className={cn(
              "flex-1 rounded-md px-4 py-1.5 text-sm font-medium border",
              overall === "yes"
                ? "bg-green-600 text-white border-green-600"
                : "bg-white border-gray-300 text-gray-600 hover:border-green-300",
            )}
          >
            ANO
          </button>
          <button
            type="button"
            onClick={() => setOverall("conditional")}
            className={cn(
              "flex-1 rounded-md px-4 py-1.5 text-sm font-medium border",
              overall === "conditional"
                ? "bg-amber-600 text-white border-amber-600"
                : "bg-white border-gray-300 text-gray-600 hover:border-amber-300",
            )}
          >
            Podmíněný
          </button>
          <button
            type="button"
            onClick={() => setOverall("no")}
            className={cn(
              "flex-1 rounded-md px-4 py-1.5 text-sm font-medium border",
              overall === "no"
                ? "bg-red-600 text-white border-red-600"
                : "bg-white border-gray-300 text-gray-600 hover:border-red-300",
            )}
          >
            NE
          </button>
        </div>
        {overall === "conditional" && (
          <p className="text-xs text-amber-800 mt-2 italic">
            ⚠ Do poznámky uveďte konkrétní závadu a omezení provozu.
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="entry-notes">Poznámky / problémy</Label>
        <textarea
          id="entry-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
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
        <Button type="submit" loading={isSubmitting}>Uložit zápis</Button>
      </div>
    </form>
  );
}

// ── Detail zařízení s tabulkou zápisů ──────────────────────────────────────

function DeviceDetail({ device }: { device: OperatingLogDevice }) {
  const qc = useQueryClient();
  const [entryOpen, setEntryOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: entries = [], isLoading } = useQuery<OperatingLogEntry[]>({
    queryKey: ["operating-logs", "entries", device.id],
    queryFn: () => api.get(`/operating-logs/devices/${device.id}/entries`),
  });

  const createEntry = useMutation({
    mutationFn: (d: Parameters<Parameters<typeof EntryForm>[0]["onSubmit"]>[0]) =>
      api.post<OperatingLogEntry>(
        `/operating-logs/devices/${device.id}/entries`,
        d,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["operating-logs", "entries", device.id] });
      setEntryOpen(false);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  function fmtDate(s: string) {
    return new Date(s).toLocaleDateString("cs-CZ");
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-gray-200 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-gray-400 uppercase">
              {DEVICE_CATEGORY_LABELS[device.category]}
            </p>
            <h3 className="text-lg font-semibold text-gray-900">{device.title}</h3>
            {device.device_code && (
              <p className="text-xs text-gray-500">Kód: {device.device_code}</p>
            )}
            {device.location && (
              <p className="text-xs text-gray-500">{device.location}</p>
            )}
            <p className="text-xs text-gray-500 mt-1">
              Periodicita: {OPERATING_PERIOD_LABELS[device.period]}
              {device.period_note && ` (${device.period_note})`}
            </p>
          </div>
          <Button onClick={() => { setServerError(null); setEntryOpen(true); }}>
            <ClipboardList className="h-4 w-4 mr-1.5" />
            Nový zápis
          </Button>
        </div>
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500 mb-1.5">Kontrolní úkony:</p>
          <ol className="text-xs text-gray-600 space-y-0.5 list-decimal pl-5">
            {device.check_items.map((it, i) => <li key={i}>{it}</li>)}
          </ol>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <p className="text-xs font-medium text-gray-500">Záznamy ({entries.length})</p>
          </div>
          {isLoading ? (
            <div className="p-6 text-sm text-gray-400">Načítám…</div>
          ) : entries.length === 0 ? (
            <div className="py-12 text-center text-gray-400">
              <ClipboardList className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Žádné zápisy</p>
              <p className="text-xs">Pro nové zařízení vytvoř první denní zápis</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-white">
                    <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Datum</th>
                    <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Kontroloval</th>
                    <th className="text-center py-2 px-4 text-xs font-medium text-gray-500">Způsobilý k provozu</th>
                    <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Položky</th>
                    <th className="text-left py-2 px-4 text-xs font-medium text-gray-500">Poznámky</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {entries.map((e) => {
                    const yesCnt = e.capable_items.filter((s) => s === "yes").length;
                    const condCnt = e.capable_items.filter((s) => s === "conditional").length;
                    const noCnt = e.capable_items.filter((s) => s === "no").length;
                    return (
                      <tr key={e.id}>
                        <td className="py-2 px-4 text-gray-700">{fmtDate(e.performed_at)}</td>
                        <td className="py-2 px-4 text-gray-700">{e.performed_by_name}</td>
                        <td className="py-2 px-4 text-center">
                          {e.overall_status === "yes" && (
                            <span className="rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-xs font-medium">ANO</span>
                          )}
                          {e.overall_status === "conditional" && (
                            <span className="rounded-full bg-amber-100 text-amber-700 px-2 py-0.5 text-xs font-medium">Podmíněný</span>
                          )}
                          {e.overall_status === "no" && (
                            <span className="rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-xs font-medium">NE</span>
                          )}
                        </td>
                        <td className="py-2 px-4 text-xs text-gray-600">
                          <span className="text-green-700">{yesCnt}</span>
                          {condCnt > 0 && <> · <span className="text-amber-700">{condCnt}</span></>}
                          {noCnt > 0 && <> · <span className="text-red-700">{noCnt}</span></>}
                        </td>
                        <td className="py-2 px-4 text-xs text-gray-500">{e.notes || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={entryOpen}
        onClose={() => setEntryOpen(false)}
        title={`Nový zápis — ${device.title}`}
        size="lg"
      >
        <EntryForm
          device={device}
          onSubmit={(d) => createEntry.mutate(d)}
          isSubmitting={createEntry.isPending}
          serverError={serverError}
        />
      </Dialog>
    </div>
  );
}

// ── Stránka ─────────────────────────────────────────────────────────────────

export default function OperatingLogsPage() {
  const qc = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [plantFilter, setPlantFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editDevice, setEditDevice] = useState<OperatingLogDevice | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: devices = [], isLoading } = useQuery<OperatingLogDevice[]>({
    queryKey: ["operating-logs", "devices", categoryFilter, plantFilter],
    queryFn: () => {
      const p = new URLSearchParams();
      if (categoryFilter) p.set("category", categoryFilter);
      if (plantFilter) p.set("plant_id", plantFilter);
      p.set("device_status", "active");
      return api.get(`/operating-logs/devices?${p.toString()}`);
    },
  });

  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants?plant_status=active"),
    staleTime: 5 * 60 * 1000,
  });

  const selected = devices.find((d) => d.id === selectedId) ?? null;

  const createMut = useMutation({
    mutationFn: (data: DeviceFormData) =>
      api.post<OperatingLogDevice>("/operating-logs/devices", {
        ...data,
        plant_id: data.plant_id || null,
        device_code: data.device_code || null,
        location: data.location || null,
        period_note: data.period_note || null,
        notes: data.notes || null,
        check_items: data.check_items.map((c) => c.value).filter(Boolean),
        responsible_employee_id: data.responsible_employee_id || null,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["operating-logs"] });
      setCreateOpen(false);
      setSelectedId(res.id);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: DeviceFormData }) =>
      api.patch(`/operating-logs/devices/${id}`, {
        title: data.title,
        device_code: data.device_code || null,
        location: data.location || null,
        plant_id: data.plant_id || null,
        period: data.period,
        period_note: data.period_note || null,
        notes: data.notes || null,
        check_items: data.check_items.map((c) => c.value).filter(Boolean),
        responsible_employee_id: data.responsible_employee_id || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["operating-logs"] });
      setEditDevice(null);
      setServerError(null);
    },
    onError: (err) => setServerError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const archiveMut = useMutation({
    mutationFn: (id: string) => api.delete(`/operating-logs/devices/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["operating-logs"] });
      if (selected) setSelectedId(null);
    },
  });

  return (
    <div>
      <Header
        title="Provozní deníky"
        actions={
          <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
            <Plus className="h-4 w-4 mr-1.5" />
            Přidat zařízení
          </Button>
        }
      />

      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Levý panel: list */}
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 bg-gray-50 border border-gray-200 rounded-md p-2">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">Všechny kategorie</option>
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>{c.label.split(" (")[0]}</option>
              ))}
            </select>
            <select
              value={plantFilter}
              onChange={(e) => setPlantFilter(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">Všechny plant</option>
              {plants.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="p-3 space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-12 bg-gray-50 rounded animate-pulse" />
                  ))}
                </div>
              ) : devices.length === 0 ? (
                <div className="py-12 text-center text-gray-400">
                  <BookOpenCheck className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">Žádná zařízení</p>
                  <p className="text-xs">Přidejte první stroj/zařízení s provozním deníkem</p>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100">
                  {devices.map((d) => {
                    const active = d.id === selectedId;
                    return (
                      <li key={d.id}>
                        <button
                          onClick={() => setSelectedId(d.id)}
                          className={cn(
                            "w-full text-left px-4 py-3 hover:bg-gray-50",
                            active && "bg-blue-50 hover:bg-blue-50",
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className={cn(
                                "text-sm truncate",
                                active ? "font-semibold text-blue-700" : "font-medium text-gray-900"
                              )}>
                                {d.title}
                              </p>
                              <p className="text-[10px] text-gray-400 uppercase mt-0.5">
                                {DEVICE_CATEGORY_LABELS[d.category].split(" (")[0]}
                              </p>
                              {d.plant_name && (
                                <p className="text-xs text-gray-500 mt-0.5">{d.plant_name}</p>
                              )}
                            </div>
                            <span className="text-[10px] text-gray-400 shrink-0">
                              {OPERATING_PERIOD_LABELS[d.period]}
                            </span>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Pravý panel */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="space-y-3">
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    window.open(
                      `/api/v1/operating-logs/devices/${selected.id}/qr.png`,
                      "_blank",
                    )
                  }
                >
                  <QrCode className="h-3.5 w-3.5 mr-1" /> QR kód
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setServerError(null); setEditDevice(selected); }}
                >
                  <Pencil className="h-3.5 w-3.5 mr-1" /> Upravit zařízení
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (confirm(`Archivovat zařízení „${selected.title}“?`))
                      archiveMut.mutate(selected.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5 mr-1" /> Archivovat
                </Button>
              </div>
              <DeviceDetail device={selected} />
            </div>
          ) : (
            <Card>
              <CardContent className="p-12 text-center text-gray-400">
                <BookOpenCheck className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">Vyber zařízení vlevo</p>
                <p className="text-xs mt-1">Nebo přidej nové strojní zařízení s deníkem</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Přidat zařízení do provozního deníku"
        size="lg"
      >
        <DeviceForm
          plants={plants}
          onSubmit={(d) => createMut.mutate(d)}
          isSubmitting={createMut.isPending}
          serverError={serverError}
        />
      </Dialog>

      <Dialog
        open={!!editDevice}
        onClose={() => setEditDevice(null)}
        title={editDevice ? `Upravit: ${editDevice.title}` : ""}
        size="lg"
      >
        {editDevice && (
          <DeviceForm
            plants={plants}
            defaultValues={{
              category: editDevice.category,
              title: editDevice.title,
              device_code: editDevice.device_code ?? "",
              location: editDevice.location ?? "",
              plant_id: editDevice.plant_id ?? "",
              period: editDevice.period,
              period_note: editDevice.period_note ?? "",
              notes: editDevice.notes ?? "",
              check_items: editDevice.check_items.map((v) => ({ value: v })),
              responsible_employee_id: editDevice.responsible_employee_id ?? "",
            }}
            onSubmit={(d) => updateMut.mutate({ id: editDevice.id, data: d })}
            isSubmitting={updateMut.isPending}
            serverError={serverError}
          />
        )}
      </Dialog>
    </div>
  );
}
