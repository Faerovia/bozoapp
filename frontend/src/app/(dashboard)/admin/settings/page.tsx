"use client";

/**
 * Globální nastavení platformy. Přístup: jen platform admin.
 *
 * Editor každého settingu jako JSON textarea — bezpečný univerzální editor
 * pro JSONB hodnoty. Specializované UI pro nejčastější keys (např. lhůty
 * prohlídek) lze přidat později.
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, AlertTriangle, RotateCcw, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface PlatformSetting {
  key: string;
  value: unknown;
  description: string | null;
  updated_by: string | null;
  updated_at: string;
}

const FRIENDLY_LABELS: Record<string, string> = {
  "medical_exam.periodicity_months":
    "Lhůty preventivních prohlídek (měsíce dle kategorie + věku)",
  "medical_exam.factor_to_specialties":
    "Mapování rizikový faktor → odborné prohlídky",
  "medical_exam.specialty_periodicity_months":
    "Periodicita odborných prohlídek (měsíce dle ratingu faktoru)",
  "medical_exam.expiring_soon_days":
    "Varovat na expirující prohlídky X dní předem",
  "medical_exam.auto_check_throttle_minutes":
    "Throttle pro auto-generaci prohlídek (minuty)",
};

function SettingEditor({
  setting,
  onSave,
}: {
  setting: PlatformSetting;
  onSave: (key: string, value: unknown) => Promise<void>;
}) {
  const [text, setText] = useState(JSON.stringify(setting.value, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const isDirty = text !== JSON.stringify(setting.value, null, 2);

  useEffect(() => {
    setText(JSON.stringify(setting.value, null, 2));
    setError(null);
  }, [setting.value]);

  async function handleSave() {
    setError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(`Neplatný JSON: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    setSaving(true);
    try {
      await onSave(setting.key, parsed);
      setSavedAt(new Date().toLocaleTimeString("cs-CZ"));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Chyba ukládání");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setText(JSON.stringify(setting.value, null, 2));
    setError(null);
  }

  const friendly = FRIENDLY_LABELS[setting.key] || setting.key;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{friendly}</h3>
          <p className="text-xs text-gray-400 font-mono mt-0.5">{setting.key}</p>
          {setting.description && (
            <p className="text-xs text-gray-600 mt-2">{setting.description}</p>
          )}
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={Math.min(text.split("\n").length + 1, 18)}
          className="w-full font-mono text-xs rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          spellCheck={false}
        />

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
            <AlertTriangle className="h-3.5 w-3.5 inline mr-1" />
            {error}
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">
            {savedAt
              ? `Uloženo v ${savedAt}`
              : `Naposledy upraveno: ${new Date(setting.updated_at).toLocaleString("cs-CZ")}`}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              onClick={handleReset}
              disabled={!isDirty || saving}
            >
              <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reset
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!isDirty || saving}
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Uložit
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdminSettingsPage() {
  const qc = useQueryClient();

  const { data: settings = [], isLoading, isError } = useQuery<PlatformSetting[]>({
    queryKey: ["admin-settings"],
    queryFn: () => api.get("/admin/settings"),
  });

  const saveMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      api.patch(`/admin/settings/${encodeURIComponent(key)}`, { value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
  });

  if (isError) {
    return (
      <div>
        <Header title="Globální nastavení" />
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
      <Header title="Globální nastavení platformy" />

      <div className="p-6 space-y-4">
        <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 text-xs text-blue-800">
          Změny zde se aplikují <strong>okamžitě napříč všemi tenanty</strong>.
          Hodnoty čte service vrstva při vytváření prohlídek a auto-generaci.
          Při neplatném JSONu se uložení odmítne.
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-gray-400 py-12 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" /> Načítám…
          </div>
        ) : settings.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center text-gray-400 text-sm">
              Žádná nastavení. Inicializuj migracemi.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {settings.map(s => (
              <SettingEditor
                key={s.key}
                setting={s}
                onSave={async (key, value) => {
                  await saveMutation.mutateAsync({ key, value });
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
