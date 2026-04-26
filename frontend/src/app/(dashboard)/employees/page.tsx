"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { UserPlus, Pencil, UserX, Download, RefreshCw, Copy, Upload, FileText } from "lucide-react";
import { api, ApiError, uploadFile } from "@/lib/api";
import { useTableSort } from "@/lib/use-table-sort";
import { SortableHeader } from "@/components/ui/sortable-header";
import type { Employee, EmploymentType, JobPosition, Plant, Workplace } from "@/types/api";
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

  // Identifikace
  personal_id:      z.string().optional(),       // rodné číslo
  personal_number:  z.string().optional(),       // osobní číslo ve firmě
  birth_date:       z.string().optional(),
  gender:           z.enum(["M", "F", "X"] as const).or(z.literal("")).optional()
                     .transform(v => v === "" ? null : (v ?? null)),

  // Kontakt — email je povinný (vytvoří přihlašovací účet)
  email:            z.string().email("Neplatný email"),
  phone:            z.string().optional(),

  // Heslo — frontend ho negeneruje, server ho vygeneruje při create
  // a vrátí v generated_password. Editace pomocí refresh tlačítka.
  user_password:    z.string().optional(),

  // Trvalé bydliště
  address_street:   z.string().optional(),
  address_city:     z.string().optional(),
  address_zip:      z.string().optional(),

  // Pracovní zařazení
  plant_id:         z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
  workplace_id:     z.string().uuid().or(z.literal("")).optional().transform(v => v || null),
  job_position_id:  z.string().uuid().or(z.literal("")).optional().transform(v => v || null),

  hired_at:         z.string().optional(),
  notes:            z.string().optional(),

  is_equipment_responsible: z.boolean().default(false),
  // Provozovny, za které je zaměstnanec zodpovědný (pro revize). M:N mapping.
  // Při create/update se posílá do backendu spolu s is_equipment_responsible.
  responsible_plant_ids: z.array(z.string().uuid()).default([]),
  // Tenant-level role propojeného User účtu — výběr OZO/HR/lead_worker/...
  assigned_role: z.enum([
    "ozo", "hr_manager", "lead_worker", "equipment_responsible", "employee",
  ] as const).default("employee"),
});

type FormData = z.infer<typeof schema>;

const SELECT_CLS = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

// ── Position select (filtr podle workplace + inline create) ────────────────

function PositionSelect({
  value,
  onChange,
  selectedWorkplaceId,
  allPositions,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
  selectedWorkplaceId: string | null | undefined;
  allPositions: JobPosition[];
}) {
  const qc = useQueryClient();
  const [addingNew, setAddingNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  // Filtr podle vybraného pracoviště; jinak prázdný seznam
  const filtered = selectedWorkplaceId
    ? allPositions.filter((p) => p.workplace_id === selectedWorkplaceId)
    : [];

  const createPosition = useMutation({
    mutationFn: (name: string) =>
      api.post<JobPosition>("/job-positions", {
        workplace_id: selectedWorkplaceId!,
        name,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["job-positions"] });
      onChange(res.id);
      setAddingNew(false);
      setNewName("");
      setSaveError(null);
    },
    onError: (err) => setSaveError(err instanceof ApiError ? err.detail : "Chyba serveru"),
  });

  const disabled = !selectedWorkplaceId;

  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <select
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
          className={SELECT_CLS}
          disabled={disabled}
        >
          <option value="">— Nevybráno —</option>
          {filtered.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.effective_category ? ` (kat. ${p.effective_category})` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setAddingNew(!addingNew)}
          disabled={disabled}
          className="whitespace-nowrap rounded-md border border-gray-300 px-3 py-2 text-xs font-medium text-gray-600 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          + Nová pozice
        </button>
      </div>

      {addingNew && !disabled && (
        <div className="rounded-md border border-blue-100 bg-blue-50/40 p-2 space-y-2">
          <div className="flex gap-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Název nové pozice"
              className="flex-1"
            />
            <Button
              type="button"
              size="sm"
              disabled={!newName.trim() || createPosition.isPending}
              loading={createPosition.isPending}
              onClick={() => createPosition.mutate(newName.trim())}
            >
              Uložit
            </Button>
          </div>
          <p className="text-xs text-gray-500">
            Pozice se vytvoří pod vybraným pracovištěm a automaticky se přiřadí zaměstnanci.
          </p>
          {saveError && (
            <p className="text-xs text-red-600">{saveError}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Formulář ─────────────────────────────────────────────────────────────────

function EmployeeForm({
  defaultValues,
  onSubmit,
  isSubmitting,
  serverError,
  jobPositions,
  plants,
  workplaces,
  isEdit = false,
  editUserId = null,
  onRegeneratePassword,
}: {
  defaultValues?: Partial<FormData>;
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  jobPositions: JobPosition[];
  plants: Plant[];
  workplaces: Workplace[];
  isEdit?: boolean;
  editUserId?: string | null;
  onRegeneratePassword?: (userId: string) => void;
}) {
  const { register, handleSubmit, watch, setValue, formState: { errors } } =
    useForm<FormData>({
      resolver: zodResolver(schema),
      defaultValues: defaultValues ?? {
        employment_type: "hpp",
        is_equipment_responsible: false,
        responsible_plant_ids: [],
      },
    });

  // Cascading dropdown: Plant → Workplace
  const selectedPlant = watch("plant_id");
  const selectedWorkplace = watch("workplace_id");
  const availableWorkplaces = selectedPlant
    ? workplaces.filter(w => w.plant_id === selectedPlant)
    : workplaces;

  // Pokud se změní Plant, ale aktuální workplace nepatří do něj → vymazat
  const workplaceValid = availableWorkplaces.some(w => w.id === selectedWorkplace);
  if (selectedPlant && selectedWorkplace && !workplaceValid) {
    setValue("workplace_id", null);
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* Jméno + příjmení */}
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

      {/* Typ úvazku + Role */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="employment_type">Typ úvazku *</Label>
          <select id="employment_type" {...register("employment_type")} className={SELECT_CLS}>
            {EMPLOYMENT_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="assigned_role">Role v aplikaci *</Label>
          <select id="assigned_role" {...register("assigned_role")} className={SELECT_CLS}>
            <option value="employee">Zaměstnanec</option>
            <option value="lead_worker">Vedoucí pracovník</option>
            <option value="equipment_responsible">Zaměstnanec — zodpovědný za vyhrazená zařízení</option>
            <option value="hr_manager">HR manager</option>
            <option value="ozo">OZO BOZP/PO</option>
          </select>
          <p className="text-xs text-gray-400">
            Určuje co všechno zaměstnanec vidí v aplikaci po přihlášení.
          </p>
        </div>
      </div>

      {/* Multi-select provozoven pro zodpovědnost — když má role equipment_responsible */}
      {watch("assigned_role") === "equipment_responsible" && (
        <div className="space-y-1.5 rounded-md border border-blue-100 bg-blue-50/30 p-3">
          <Label>Zodpovědné provozovny</Label>
          <p className="text-xs text-gray-500 -mt-1 mb-2">
            Vyber provozovny, za které bude zaměstnanec zodpovědný.
            Notifikace o blížících se revizích dostane e-mailem.
          </p>
          {plants.length === 0 ? (
            <p className="text-xs text-gray-400">Nejprve vytvořte provozovnu</p>
          ) : (
            <div className="space-y-1.5 max-h-40 overflow-auto">
              {plants.map(p => {
                const selected = (watch("responsible_plant_ids") ?? []).includes(p.id);
                return (
                  <label key={p.id} className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={(e) => {
                        const curr = watch("responsible_plant_ids") ?? [];
                        const next = e.target.checked
                          ? [...curr, p.id]
                          : curr.filter((id: string) => id !== p.id);
                        setValue("responsible_plant_ids", next, { shouldDirty: true });
                      }}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span>{p.name}</span>
                    {p.city && <span className="text-xs text-gray-400">{p.city}</span>}
                  </label>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Provozovna (plant) → Pracoviště (workplace) — cascading */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="plant_id">Provozovna</Label>
          <select id="plant_id" {...register("plant_id")} className={SELECT_CLS}>
            <option value="">— Nevybráno —</option>
            {plants.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          {plants.length === 0 && (
            <p className="text-xs text-gray-400">Nejprve vytvořte provozovnu</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="workplace_id">Pracoviště</Label>
          <select
            id="workplace_id"
            {...register("workplace_id")}
            className={SELECT_CLS}
            disabled={!selectedPlant && plants.length > 0}
          >
            <option value="">— Nevybráno —</option>
            {availableWorkplaces.map(w => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
          {selectedPlant && availableWorkplaces.length === 0 && (
            <p className="text-xs text-gray-400">Žádná pracoviště v této provozovně</p>
          )}
          {!selectedPlant && plants.length > 0 && (
            <p className="text-xs text-gray-400">Nejprve vyberte provozovnu</p>
          )}
        </div>
      </div>

      {/* Pracovní pozice */}
      <div className="space-y-1.5">
        <Label htmlFor="job_position_id">Pracovní pozice</Label>
        <PositionSelect
          value={watch("job_position_id") ?? null}
          onChange={(id) => setValue("job_position_id", id, { shouldDirty: true })}
          selectedWorkplaceId={selectedWorkplace}
          allPositions={jobPositions}
        />
        {!selectedPlant && (
          <p className="text-xs text-gray-400">Nejprve vyberte provozovnu</p>
        )}
        {selectedPlant && !selectedWorkplace && (
          <p className="text-xs text-gray-400">Nejprve vyberte pracoviště</p>
        )}
      </div>

      {/* Email + Heslo (s refresh tlačítkem) */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email *</Label>
          <Input id="email" type="email" {...register("email")} />
          {errors.email && <p className="text-xs text-red-600">{errors.email.message}</p>}
          {!isEdit && (
            <p className="text-xs text-gray-400">
              Z emailu bude uživatelské jméno pro přihlášení.
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="user_password">Heslo</Label>
          <div className="flex gap-2">
            <Input
              id="user_password"
              type="text"
              value={
                isEdit
                  ? (editUserId ? "••••••••" : "Bez účtu")
                  : "(vygeneruje se po uložení)"
              }
              disabled
              className="flex-1 font-mono text-xs"
            />
            {isEdit && editUserId && onRegeneratePassword && (
              <button
                type="button"
                onClick={() => {
                  if (confirm("Vygenerovat nové heslo? Uživatel bude muset znovu přihlásit.")) {
                    onRegeneratePassword(editUserId);
                  }
                }}
                className="rounded-md border border-gray-300 px-3 text-gray-600 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-colors"
                title="Vygenerovat nové heslo"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
            )}
          </div>
          {isEdit && !editUserId && (
            <p className="text-xs text-amber-600">
              Tento zaměstnanec nemá přihlašovací účet (vytvořen před zavedením auto-účtů).
            </p>
          )}
        </div>
      </div>

      {/* Telefon */}
      <div className="space-y-1.5">
        <Label htmlFor="phone">Telefon</Label>
        <Input id="phone" {...register("phone")} />
      </div>

      {/* Identifikace */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="personal_id">Rodné číslo</Label>
          <Input id="personal_id" placeholder="YYMMDD/XXXX" {...register("personal_id")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="personal_number">Osobní číslo</Label>
          <Input
            id="personal_number"
            placeholder="např. 2024-001"
            {...register("personal_number")}
          />
        </div>
      </div>

      {/* Datum narození + nástupu + pohlaví */}
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="birth_date">Datum narození</Label>
          <Input id="birth_date" type="date" {...register("birth_date")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="hired_at">Datum nástupu</Label>
          <Input id="hired_at" type="date" {...register("hired_at")} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="gender">Pohlaví</Label>
          <select id="gender" {...register("gender")} className={SELECT_CLS}>
            <option value="">— neuvedeno —</option>
            <option value="M">Muž</option>
            <option value="F">Žena</option>
            <option value="X">Jiné</option>
          </select>
        </div>
      </div>

      {/* Trvalé bydliště */}
      <div className="border-t border-gray-100 pt-4">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
          Trvalé bydliště
        </p>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="address_street">Ulice a č.p.</Label>
            <Input id="address_street" {...register("address_street")} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5 col-span-2">
              <Label htmlFor="address_city">Město</Label>
              <Input id="address_city" {...register("address_city")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="address_zip">PSČ</Label>
              <Input id="address_zip" placeholder="000 00" {...register("address_zip")} />
            </div>
          </div>
        </div>
      </div>

      {/* Poznámky */}
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

// ── Import response typy ─────────────────────────────────────────────────────

interface ImportSuccessRow {
  row: number;
  employee_id: string;
  full_name: string;
  email: string | null;
  generated_password: string | null;
}
interface ImportErrorRow {
  row: number;
  error: string;
  raw: Record<string, string>;
}
interface ImportResponse {
  total_rows: number;
  created_count: number;
  error_count: number;
  created: ImportSuccessRow[];
  errors: ImportErrorRow[];
}

// ── Import dialog ────────────────────────────────────────────────────────────

function ImportDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function downloadTemplate() {
    // Přímý download přes browser (server endpoint vrátí CSV attachment).
    // Musíme přes window.open aby cookies + proxy fungovalo správně.
    window.open("/api/v1/employees/import/template", "_blank");
  }

  async function submit() {
    if (!file) return;
    setError(null);
    setIsUploading(true);
    try {
      const res = await uploadFile<ImportResponse>("/employees/import", file);
      setResult(res);
      if (res.created_count > 0) onImported();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Nahrávání selhalo");
    } finally {
      setIsUploading(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Import zaměstnanců z CSV" size="lg">
      {!result ? (
        <div className="space-y-5">
          {/* Vzor ke stažení */}
          <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
            <div className="flex items-start gap-3">
              <FileText className="h-5 w-5 shrink-0 text-blue-600 mt-0.5" />
              <div className="flex-1 text-sm">
                <p className="font-medium text-blue-900">Nepřipravili jste soubor?</p>
                <p className="mt-1 text-blue-800">
                  Stáhněte si vzorový CSV s přesnou hlavičkou a příkladem.
                  Otevřete ho v Excelu, doplňte zaměstnance a nahrajte zpět.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={downloadTemplate}>
                <Download className="h-3.5 w-3.5 mr-1" />
                Vzor CSV
              </Button>
            </div>
          </div>

          {/* Informace o formátu */}
          <div className="text-xs text-gray-600 space-y-1">
            <p className="font-medium">Požadavky na soubor:</p>
            <ul className="list-disc list-inside space-y-0.5 pl-2">
              <li>Formát .csv (UTF-8, oddělovač čárka nebo středník)</li>
              <li>Povinné sloupce: <code className="bg-gray-100 px-1 rounded">first_name</code>, <code className="bg-gray-100 px-1 rounded">last_name</code></li>
              <li>Provozovna / pracoviště / pozice — zadejte <strong>přesný název</strong> (musí už existovat v systému)</li>
              <li>Datum ve formátu <code className="bg-gray-100 px-1 rounded">YYYY-MM-DD</code></li>
              <li>Boolean (is_equipment_responsible / create_user_account): <code className="bg-gray-100 px-1 rounded">true</code> / <code className="bg-gray-100 px-1 rounded">false</code></li>
              <li>Max 5 MB na soubor</li>
            </ul>
          </div>

          {/* Upload */}
          <div className="space-y-1.5">
            <Label htmlFor="csv_file">Vyberte CSV soubor</Label>
            <input
              id="csv_file"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
            />
            {file && (
              <p className="text-xs text-gray-500">
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          {error && (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <Button variant="outline" onClick={handleClose}>Zrušit</Button>
            <Button onClick={submit} disabled={!file} loading={isUploading}>
              <Upload className="h-4 w-4 mr-1.5" />
              Importovat
            </Button>
          </div>
        </div>
      ) : (
        <ImportResult result={result} onClose={handleClose} onReset={reset} />
      )}
    </Dialog>
  );
}

// ── Import výsledek ──────────────────────────────────────────────────────────

function ImportResult({
  result,
  onClose,
  onReset,
}: {
  result: ImportResponse;
  onClose: () => void;
  onReset: () => void;
}) {
  const passwordsToShow = result.created.filter(r => r.generated_password);

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-md bg-gray-100 p-3">
          <div className="text-2xl font-semibold text-gray-900">{result.total_rows}</div>
          <div className="text-xs text-gray-500">Celkem řádků</div>
        </div>
        <div className="rounded-md bg-green-100 p-3">
          <div className="text-2xl font-semibold text-green-800">{result.created_count}</div>
          <div className="text-xs text-green-700">Vytvořeno</div>
        </div>
        <div className={cn(
          "rounded-md p-3",
          result.error_count > 0 ? "bg-red-100" : "bg-gray-50"
        )}>
          <div className={cn(
            "text-2xl font-semibold",
            result.error_count > 0 ? "text-red-800" : "text-gray-400"
          )}>
            {result.error_count}
          </div>
          <div className={cn(
            "text-xs",
            result.error_count > 0 ? "text-red-700" : "text-gray-400"
          )}>
            Chyb
          </div>
        </div>
      </div>

      {/* Vygenerovaná hesla */}
      {passwordsToShow.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4">
          <p className="text-sm font-medium text-amber-900 mb-2">
            Vygenerovaná hesla ({passwordsToShow.length}) — zapište si je hned, znovu se nezobrazí:
          </p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-amber-800 border-b border-amber-200">
                <th className="py-1 pr-2">Jméno</th>
                <th className="py-1 pr-2">Email</th>
                <th className="py-1">Heslo</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {passwordsToShow.map(r => (
                <tr key={r.employee_id} className="border-b border-amber-100">
                  <td className="py-1 pr-2 whitespace-nowrap">{r.full_name}</td>
                  <td className="py-1 pr-2 text-gray-700">{r.email}</td>
                  <td className="py-1 text-amber-900 font-semibold select-all">{r.generated_password}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            onClick={() => {
              const text = passwordsToShow
                .map(r => `${r.full_name}\t${r.email ?? ""}\t${r.generated_password}`)
                .join("\n");
              navigator.clipboard.writeText(text);
            }}
            className="mt-2 text-xs text-amber-800 hover:text-amber-900 underline"
          >
            Zkopírovat do schránky (tab-separated)
          </button>
        </div>
      )}

      {/* Chyby */}
      {result.errors.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-red-800">
            Řádky které se nepodařilo importovat:
          </p>
          <div className="max-h-60 overflow-y-auto rounded-md border border-red-200">
            <table className="w-full text-xs">
              <thead className="bg-red-50 sticky top-0">
                <tr>
                  <th className="text-left py-2 px-3 font-medium text-red-800">Řádek</th>
                  <th className="text-left py-2 px-3 font-medium text-red-800">Chyba</th>
                </tr>
              </thead>
              <tbody>
                {result.errors.map((e, i) => (
                  <tr key={i} className="border-t border-red-100">
                    <td className="py-1.5 px-3 align-top font-mono">{e.row}</td>
                    <td className="py-1.5 px-3 text-red-700">{e.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
        <Button variant="outline" onClick={onReset}>Importovat další</Button>
        <Button onClick={onClose}>Zavřít</Button>
      </div>
    </div>
  );
}

// ── Heslo modal (po úspěšném vytvoření nebo regeneraci) ─────────────────────

function PasswordModal({
  open,
  password,
  email,
  onClose,
}: {
  open: boolean;
  password: string | null;
  email: string | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Dialog open={open} onClose={onClose} title="Vygenerované heslo" size="sm">
      {password && (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">
            {email
              ? <>Pro uživatele <strong>{email}</strong>:</>
              : "Nové heslo:"}
          </p>
          <div className="flex items-center gap-2 rounded-md bg-gray-100 p-3 font-mono text-sm">
            <code className="flex-1 select-all">{password}</code>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(password);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="rounded p-1.5 text-gray-500 hover:bg-white hover:text-blue-600 transition-colors"
              title="Kopírovat"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          {copied && <p className="text-xs text-green-600">Zkopírováno do schránky.</p>}
          <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
            Heslo se zobrazí pouze TEĎ. Předejte ho uživateli, který si ho po
            přihlášení může změnit.
          </div>
          <div className="flex justify-end">
            <Button onClick={onClose}>Rozumím</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

// ── Stránka ───────────────────────────────────────────────────────────────────

export default function EmployeesPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [plantFilter, setPlantFilter] = useState<string>("");
  const [workplaceFilter, setWorkplaceFilter] = useState<string>("");
  const [positionFilter, setPositionFilter] = useState<string>("");
  const [genderFilter, setGenderFilter] = useState<string>("");
  const [editEmployee, setEditEmployee] = useState<Employee | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [passwordModal, setPasswordModal] = useState<{ password: string; email: string | null } | null>(null);

  const { data: employeesRaw = [], isLoading } = useQuery<Employee[]>({
    queryKey: ["employees", statusFilter, plantFilter, workplaceFilter, positionFilter, genderFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter)    params.set("emp_status", statusFilter);
      if (plantFilter)     params.set("plant_id", plantFilter);
      if (workplaceFilter) params.set("workplace_id", workplaceFilter);
      if (positionFilter)  params.set("job_position_id", positionFilter);
      if (genderFilter)    params.set("gender", genderFilter);
      const qs = params.toString();
      return api.get(`/employees${qs ? `?${qs}` : ""}`);
    },
  });
  const {
    sortedItems: employees,
    sortKey, sortDir, toggleSort,
  } = useTableSort<Employee>(employeesRaw, "last_name");

  const { data: jobPositions = [] } = useQuery<JobPosition[]>({
    queryKey: ["job-positions"],
    queryFn: () => api.get("/job-positions"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: plants = [] } = useQuery<Plant[]>({
    queryKey: ["plants"],
    queryFn: () => api.get("/plants"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: workplaces = [] } = useQuery<Workplace[]>({
    queryKey: ["workplaces"],
    queryFn: () => api.get("/workplaces"),
    staleTime: 5 * 60 * 1000,
  });

  const createMutation = useMutation({
    // Backend auto-creates user account when email is provided (povinné od
    // commitu 9c). Heslo vygeneruje server a vrátí v response.generated_password.
    mutationFn: (data: FormData) => api.post<Employee>("/employees", data),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["employees"] });
      setCreateOpen(false);
      if (res.generated_password) {
        setPasswordModal({ password: res.generated_password, email: res.email });
      }
    },
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

  const regenerateMutation = useMutation({
    mutationFn: (userId: string) =>
      api.post<{ new_password: string }>(`/users/${userId}/regenerate-password`),
    onSuccess: (res) => {
      setPasswordModal({ password: res.new_password, email: editEmployee?.email ?? null });
    },
    onError: (err) =>
      alert(err instanceof ApiError ? err.detail : "Nepodařilo se vygenerovat heslo"),
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
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setImportOpen(true)}
            >
              <Upload className="h-4 w-4 mr-1.5" />
              Import CSV
            </Button>
            <Button onClick={() => { setServerError(null); setCreateOpen(true); }} size="sm">
              <UserPlus className="h-4 w-4 mr-1.5" />
              Přidat zaměstnance
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-4">
        {/* Statusový filtr (rychlé záložky) */}
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

        {/* Pokročilé filtry: provozovna → pracoviště → pozice + pohlaví */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end bg-gray-50 border border-gray-200 rounded-md p-3">
          <div>
            <Label htmlFor="f-plant" className="text-xs text-gray-600">Provozovna</Label>
            <select
              id="f-plant"
              value={plantFilter}
              onChange={(e) => {
                setPlantFilter(e.target.value);
                setWorkplaceFilter("");
                setPositionFilter("");
              }}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              {plants.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="f-workplace" className="text-xs text-gray-600">Pracoviště</Label>
            <select
              id="f-workplace"
              value={workplaceFilter}
              onChange={(e) => {
                setWorkplaceFilter(e.target.value);
                setPositionFilter("");
              }}
              disabled={!plantFilter}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              {workplaces
                .filter((w) => !plantFilter || w.plant_id === plantFilter)
                .map((w) => (
                  <option key={w.id} value={w.id}>{w.name}</option>
                ))}
            </select>
          </div>

          <div>
            <Label htmlFor="f-position" className="text-xs text-gray-600">Pozice</Label>
            <select
              id="f-position"
              value={positionFilter}
              onChange={(e) => setPositionFilter(e.target.value)}
              disabled={!workplaceFilter}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              {jobPositions
                .filter((p) => !workplaceFilter || p.workplace_id === workplaceFilter)
                .map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
            </select>
          </div>

          <div>
            <Label htmlFor="f-gender" className="text-xs text-gray-600">Pohlaví</Label>
            <select
              id="f-gender"
              value={genderFilter}
              onChange={(e) => setGenderFilter(e.target.value)}
              className={SELECT_CLS}
            >
              <option value="">— vše —</option>
              <option value="M">Muž</option>
              <option value="F">Žena</option>
              <option value="X">Jiné / neuvedeno</option>
            </select>
          </div>

          <Button
            variant="outline"
            size="sm"
            disabled={!plantFilter && !workplaceFilter && !positionFilter && !genderFilter}
            onClick={() => {
              setPlantFilter("");
              setWorkplaceFilter("");
              setPositionFilter("");
              setGenderFilter("");
            }}
          >
            Vyčistit filtry
          </Button>
        </div>

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
                      <SortableHeader sortKey="last_name" current={sortKey} dir={sortDir} onSort={toggleSort}>Jméno</SortableHeader>
                      <SortableHeader sortKey="personal_number" current={sortKey} dir={sortDir} onSort={toggleSort}>Os. č.</SortableHeader>
                      <SortableHeader sortKey="employment_type" current={sortKey} dir={sortDir} onSort={toggleSort}>Úvazek</SortableHeader>
                      <SortableHeader sortKey="status" current={sortKey} dir={sortDir} onSort={toggleSort}>Status</SortableHeader>
                      <SortableHeader sortKey="email" current={sortKey} dir={sortDir} onSort={toggleSort}>Email</SortableHeader>
                      <SortableHeader sortKey="hired_at" current={sortKey} dir={sortDir} onSort={toggleSort}>Nástup</SortableHeader>
                      <th className="py-3 px-4" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {employees.map(emp => (
                      <tr key={emp.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-medium text-gray-900">
                          {emp.last_name} {emp.first_name}
                        </td>
                        <td className="py-3 px-4 text-gray-600 text-xs">{emp.personal_number || "—"}</td>
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
                              onClick={async () => {
                                const resp = await fetch(
                                  `/api/v1/employees/${emp.id}/trainings.pdf`,
                                );
                                if (!resp.ok) {
                                  let detail = `HTTP ${resp.status}`;
                                  try {
                                    const j = await resp.json();
                                    if (typeof j.detail === "string") detail = j.detail;
                                  } catch { /* not JSON */ }
                                  alert(`Generování souhrnu školení selhalo:\n${detail}`);
                                  return;
                                }
                                const blob = await resp.blob();
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = url;
                                a.download = `skoleni-${emp.last_name}-${emp.first_name}.pdf`;
                                a.click();
                                URL.revokeObjectURL(url);
                              }}
                              className="rounded p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                              title="Souhrn školení (PDF)"
                            >
                              <FileText className="h-3.5 w-3.5" />
                            </button>
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
          plants={plants}
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
          <EditEmployeeBody
            employee={editEmployee}
            plants={plants}
            workplaces={workplaces}
            jobPositions={jobPositions}
            onSubmit={(data) => {
              setServerError(null);
              updateMutation.mutate({ id: editEmployee.id, data });
            }}
            isSubmitting={updateMutation.isPending}
            serverError={serverError}
            onRegeneratePassword={(uid) => regenerateMutation.mutate(uid)}
          />
        )}
      </Dialog>

      {/* Dialog: Vygenerované heslo */}
      <PasswordModal
        open={!!passwordModal}
        password={passwordModal?.password ?? null}
        email={passwordModal?.email ?? null}
        onClose={() => setPasswordModal(null)}
      />

      {/* Dialog: Import CSV */}
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => qc.invalidateQueries({ queryKey: ["employees"] })}
      />
    </div>
  );
}

// ── EditEmployeeBody ───────────────────────────────────────────────────────
// Samostatná komponenta pro edit dialog — zaručuje, že se nejprve načtou
// stávající responsibilities a teprve pak se vyrenderuje formulář s
// předvyplněnými hodnotami. Bez toho by form dostal default `[]` a omylem
// by responsibilities smazal.

function EditEmployeeBody({
  employee,
  plants,
  workplaces,
  jobPositions,
  onSubmit,
  isSubmitting,
  serverError,
  onRegeneratePassword,
}: {
  employee: Employee;
  plants: Plant[];
  workplaces: Workplace[];
  jobPositions: JobPosition[];
  onSubmit: (data: FormData) => void;
  isSubmitting: boolean;
  serverError: string | null;
  onRegeneratePassword: (uid: string) => void;
}) {
  const { data: resp, isLoading } = useQuery<{ employee_id: string; plant_ids: string[] }>({
    queryKey: ["employee-responsibilities", employee.id],
    queryFn: () => api.get(`/employees/${employee.id}/responsibilities`),
  });

  if (isLoading || !resp) {
    return <div className="h-40 animate-pulse bg-gray-50 rounded" />;
  }

  return (
    <EmployeeForm
      isEdit
      editUserId={employee.user_id}
      onRegeneratePassword={onRegeneratePassword}
      defaultValues={{
        first_name:      employee.first_name,
        last_name:       employee.last_name,
        employment_type: employee.employment_type as EmploymentType,
        email:           employee.email ?? "",
        phone:           employee.phone ?? "",
        hired_at:        employee.hired_at ?? "",
        birth_date:      employee.birth_date ?? "",
        gender:          employee.gender ?? null,
        personal_id:     employee.personal_id ?? "",
        personal_number: employee.personal_number ?? "",
        address_street:  employee.address_street ?? "",
        address_city:    employee.address_city ?? "",
        address_zip:     employee.address_zip ?? "",
        notes:           employee.notes ?? "",
        plant_id:        employee.plant_id ?? null,
        workplace_id:    employee.workplace_id ?? null,
        job_position_id: employee.job_position_id ?? null,
        is_equipment_responsible: resp.plant_ids.length > 0,
        responsible_plant_ids: resp.plant_ids,
        // V edit modu default heuristika: pokud má responsible plants →
        // equipment_responsible, jinak employee. OZO může v dropdownu změnit
        // (lead_worker, hr_manager, ozo).
        assigned_role: resp.plant_ids.length > 0 ? "equipment_responsible" : "employee",
      }}
      onSubmit={onSubmit}
      isSubmitting={isSubmitting}
      serverError={serverError}
      jobPositions={jobPositions}
      plants={plants}
      workplaces={workplaces}
    />
  );
}

