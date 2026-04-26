"use client";

/**
 * Platform admin — nastavení email reminders.
 *
 * Editujeme 8 platform_settings keys (reminders.*) přes UI s validací typů.
 * Plus dvě tlačítka:
 *  - "Spustit teď" — manuální trigger cronu
 *  - "Náhled pro tenant" — co by se odeslalo bez odeslání
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Save, Loader2, AlertTriangle, RotateCcw, Bell, Play, Eye, Mail,
} from "lucide-react";
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
  updated_at: string;
}

interface RunNowResponse {
  dry_run: boolean;
  tenants_processed: number;
  emails_sent: number;
  items_total: number;
  per_tenant: {
    tenant_id: string;
    tenant_name: string;
    items_count: number;
    recipients_count: number;
    skipped: boolean;
  }[];
}

interface PreviewResponse {
  tenant_name: string;
  items_count: number;
  recipients: string[];
  subject: string | null;
  body_text: string;
}

interface TenantOverviewItem {
  id: string;
  name: string;
}

const KEYS = [
  "reminders.enabled",
  "reminders.cron_schedule",
  "reminders.thresholds.training",
  "reminders.thresholds.medical_exam",
  "reminders.thresholds.accident_followup",
  "reminders.send_to_managers",
  "reminders.send_to_equipment_responsible",
];

function valueToString(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function parseThresholds(s: string): number[] {
  return s.split(",")
    .map(p => parseInt(p.trim(), 10))
    .filter(n => !isNaN(n) && n >= 0)
    .sort((a, b) => b - a);  // descending: 30, 14, 7
}

export default function RemindersSettingsPage() {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [initial, setInitial] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  // Preview state
  const [previewTenantId, setPreviewTenantId] = useState<string>("");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);

  const { data: settings = [], isLoading } = useQuery<PlatformSetting[]>({
    queryKey: ["admin-settings"],
    queryFn: () => api.get("/admin/settings"),
  });

  const { data: tenantsResp } = useQuery<{ tenants: TenantOverviewItem[] }>({
    queryKey: ["admin-tenant-overview-min"],
    queryFn: () => api.get("/admin/tenant-overview"),
    staleTime: 60_000,
  });

  const lastRunAt = settings.find(s => s.key === "reminders.last_run_at")?.value;
  const lastRunStr = typeof lastRunAt === "string" && lastRunAt
    ? new Date(lastRunAt).toLocaleString("cs-CZ")
    : "ještě neběželo";

  useEffect(() => {
    if (settings.length > 0) {
      const next: Record<string, string> = {};
      for (const k of KEYS) {
        const s = settings.find(x => x.key === k);
        next[k] = valueToString(s?.value);
      }
      setValues(next);
      setInitial(next);
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: async (changes: { key: string; value: unknown }[]) => {
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
      setInitial({ ...values });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Chyba ukládání"),
  });

  const runNowMutation = useMutation<RunNowResponse, ApiError, boolean>({
    mutationFn: (dryRun) =>
      api.post<RunNowResponse>(`/admin/reminders/run-now?dry_run=${dryRun}`, {}),
    onSuccess: (data) => {
      const detail = data.per_tenant
        .filter(t => !t.skipped)
        .map(t => `  • ${t.tenant_name}: ${t.items_count} expirací → ${t.recipients_count} příjemců`)
        .join("\n");
      const skipped = data.per_tenant.filter(t => t.skipped).length;

      alert(
        (data.dry_run ? "DRY RUN — nic se neodeslalo.\n\n" : "") +
        `Tenanty zpracované: ${data.tenants_processed}\n` +
        `Emaily odeslané: ${data.emails_sent}\n` +
        `Celkem expirací: ${data.items_total}\n` +
        (skipped > 0 ? `Tenanty bez expirací/příjemců: ${skipped}\n` : "") +
        (detail ? "\n" + detail : ""),
      );
    },
    onError: (err) => alert(err.detail || "Cron selhal"),
  });

  const previewMutation = useMutation<PreviewResponse, ApiError, string>({
    mutationFn: (tid) => api.get<PreviewResponse>(`/admin/reminders/preview/${tid}`),
    onSuccess: (data) => setPreview(data),
    onError: (err) => alert(err.detail || "Náhled selhal"),
  });

  const dirtyKeys = KEYS.filter(k => values[k] !== initial[k]);
  const isDirty = dirtyKeys.length > 0;

  function handleSave() {
    setError(null);
    const changes = dirtyKeys.map(k => {
      let value: unknown;
      if (k === "reminders.enabled" ||
          k === "reminders.send_to_managers" ||
          k === "reminders.send_to_equipment_responsible") {
        value = values[k] === "true";
      } else if (k.startsWith("reminders.thresholds.")) {
        value = parseThresholds(values[k]);
      } else {
        value = values[k];
      }
      return { key: k, value };
    });
    saveMutation.mutate(changes);
  }

  return (
    <div>
      <Header title="Email reminders" />

      <div className="p-6 space-y-4">
        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          Reminders posílají agregovaný email s blížícími se nebo propadlými termíny
          (školení, lékařské prohlídky, akční plány úrazů). Cron běží podle{" "}
          <code>reminders.cron_schedule</code> — implementuje se na hostiteli (systemd
          timer / crontab) skript <code>python -m app.tasks.weekly_reminders</code>.
          <br/>
          Poslední běh: <strong>{lastRunStr}</strong>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-gray-400 py-12 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" /> Načítám…
          </div>
        ) : (
          <>
            {/* ── Master switch ───────────────────────────────────────────── */}
            <Card>
              <CardContent className="p-5 space-y-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                  <Bell className="h-4 w-4 text-blue-600" /> Spínač
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="enabled">Reminders aktivní</Label>
                    <select
                      id="enabled"
                      value={values["reminders.enabled"] ?? "true"}
                      onChange={(e) => setValues({ ...values, "reminders.enabled": e.target.value })}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="true">Ano — posílat upozornění</option>
                      <option value="false">Ne — vypnout všechny reminders</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="cron">Cron schedule</Label>
                    <Input
                      id="cron"
                      value={values["reminders.cron_schedule"] ?? ""}
                      onChange={(e) => setValues({ ...values, "reminders.cron_schedule": e.target.value })}
                      placeholder="0 5 * * MON"
                    />
                    <p className="text-xs text-gray-500">
                      Default: pondělí 5:00. Skutečné spouštění zajišťuje systemd/crontab
                      na hostiteli — tahle hodnota slouží pro dokumentaci.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Prahy (dnů před expirací) ────────────────────────────────── */}
            <Card>
              <CardContent className="p-5 space-y-4">
                <div className="text-sm font-semibold text-gray-700">
                  Prahové hodnoty (kolik dní před expirací upozornit)
                </div>
                <p className="text-xs text-gray-500">
                  Formát: čísla oddělená čárkou. Např. <code>30, 14, 7</code> znamená
                  poslat upozornění když do expirace zbývá ≤ 30 dní.
                </p>

                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="th-training">Školení (dny)</Label>
                    <Input
                      id="th-training"
                      value={values["reminders.thresholds.training"] ?? ""}
                      onChange={(e) => setValues({ ...values, "reminders.thresholds.training": e.target.value })}
                      placeholder="30, 14, 7"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="th-exam">Lékařské prohlídky</Label>
                    <Input
                      id="th-exam"
                      value={values["reminders.thresholds.medical_exam"] ?? ""}
                      onChange={(e) => setValues({ ...values, "reminders.thresholds.medical_exam": e.target.value })}
                      placeholder="30, 14, 7"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="th-accident">Akční plán úrazů</Label>
                    <Input
                      id="th-accident"
                      value={values["reminders.thresholds.accident_followup"] ?? ""}
                      onChange={(e) => setValues({ ...values, "reminders.thresholds.accident_followup": e.target.value })}
                      placeholder="14, 7, 0"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Příjemci ────────────────────────────────────────────────── */}
            <Card>
              <CardContent className="p-5 space-y-4">
                <div className="text-sm font-semibold text-gray-700">Příjemci</div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="r-managers">OZO + HR manageři</Label>
                    <select
                      id="r-managers"
                      value={values["reminders.send_to_managers"] ?? "true"}
                      onChange={(e) => setValues({ ...values, "reminders.send_to_managers": e.target.value })}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="true">Ano</option>
                      <option value="false">Ne</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="r-equipment">Equipment responsible</Label>
                    <select
                      id="r-equipment"
                      value={values["reminders.send_to_equipment_responsible"] ?? "true"}
                      onChange={(e) => setValues({ ...values, "reminders.send_to_equipment_responsible": e.target.value })}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="true">Ano</option>
                      <option value="false">Ne</option>
                    </select>
                  </div>
                </div>
              </CardContent>
            </Card>

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
                    ? `Změněno ${dirtyKeys.length} polí`
                    : "Žádné změny"}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setValues({ ...initial }); setError(null); }}
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
                  <Save className="h-3.5 w-3.5 mr-1" /> Uložit
                </Button>
              </div>
            </div>

            {/* ── Manual run + preview ────────────────────────────────────── */}
            <Card>
              <CardContent className="p-5 space-y-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                  <Play className="h-4 w-4 text-blue-600" /> Manuální spuštění a náhled
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      if (confirm("Spustit reminder cron NA SUCHO (dry_run, neposílá emaily)?")) {
                        runNowMutation.mutate(true);
                      }
                    }}
                    loading={runNowMutation.isPending}
                  >
                    <Eye className="h-3.5 w-3.5 mr-1" /> Spustit dry-run
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      if (confirm("Spustit reminder cron a OPRAVDU poslat emaily?")) {
                        runNowMutation.mutate(false);
                      }
                    }}
                    loading={runNowMutation.isPending}
                  >
                    <Mail className="h-3.5 w-3.5 mr-1" /> Spustit a poslat
                  </Button>
                </div>

                <div className="border-t border-gray-100 pt-4 space-y-2">
                  <Label htmlFor="preview-tenant">Náhled emailu pro konkrétní tenant</Label>
                  <div className="flex gap-2">
                    <select
                      id="preview-tenant"
                      value={previewTenantId}
                      onChange={(e) => setPreviewTenantId(e.target.value)}
                      className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">— Vyber zákazníka —</option>
                      {(tenantsResp?.tenants ?? []).map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      onClick={() => previewMutation.mutate(previewTenantId)}
                      disabled={!previewTenantId || previewMutation.isPending}
                      loading={previewMutation.isPending}
                    >
                      <Eye className="h-3.5 w-3.5 mr-1" /> Zobrazit
                    </Button>
                  </div>
                </div>

                {preview && (
                  <div className="border border-gray-200 rounded-md p-4 space-y-2 bg-gray-50">
                    <div className="text-xs text-gray-600">
                      <strong>{preview.tenant_name}</strong> — {preview.items_count} expirací,
                      {" "}{preview.recipients.length} příjemců
                      {preview.recipients.length > 0 && (
                        <span className="text-gray-400">
                          {" "}({preview.recipients.join(", ")})
                        </span>
                      )}
                    </div>
                    {preview.subject && (
                      <div className="text-sm font-semibold text-gray-900">
                        Subject: {preview.subject}
                      </div>
                    )}
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono bg-white border border-gray-100 p-3 rounded max-h-96 overflow-auto">
                      {preview.body_text}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
