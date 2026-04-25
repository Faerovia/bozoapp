"use client";

/**
 * Detail jednoho globálního nastavení. URL: /admin/settings/[slug].
 * Slug → key mapping je definovaný níže — sidebar items používají stejné slugy.
 */

import { use, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, AlertTriangle, RotateCcw, Loader2, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const SLUG_TO_KEY: Record<string, string> = {
  "medical-exam-periodicity":   "medical_exam.periodicity_months",
  "factor-to-specialties":      "medical_exam.factor_to_specialties",
  "specialty-periodicity":      "medical_exam.specialty_periodicity_months",
  "expiring-warning":           "medical_exam.expiring_soon_days",
  "auto-throttle":              "medical_exam.auto_check_throttle_minutes",
};

const SLUG_TO_LABEL: Record<string, string> = {
  "medical-exam-periodicity":   "Lhůty preventivních prohlídek (měsíce dle kategorie + věku)",
  "factor-to-specialties":      "Mapování rizikový faktor → odborné prohlídky",
  "specialty-periodicity":      "Periodicita odborných prohlídek (měsíce dle ratingu)",
  "expiring-warning":           "Varování o expiraci prohlídek (X dní předem)",
  "auto-throttle":              "Throttle pro auto-generaci prohlídek (minuty)",
};

interface PlatformSetting {
  key: string;
  value: unknown;
  description: string | null;
  updated_by: string | null;
  updated_at: string;
}

export default function AdminSettingPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const settingKey = SLUG_TO_KEY[slug];
  const friendlyLabel = SLUG_TO_LABEL[slug] || settingKey || slug;

  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [initialText, setInitialText] = useState("");

  const { data: settings = [], isLoading, isError } = useQuery<PlatformSetting[]>({
    queryKey: ["admin-settings"],
    queryFn: () => api.get("/admin/settings"),
    enabled: !!settingKey,
  });

  const setting = settings.find(s => s.key === settingKey);

  useEffect(() => {
    if (setting) {
      const json = JSON.stringify(setting.value, null, 2);
      setText(json);
      setInitialText(json);
      setError(null);
    }
  }, [setting?.value, setting]);

  const saveMutation = useMutation({
    mutationFn: (value: unknown) =>
      api.patch(`/admin/settings/${encodeURIComponent(settingKey)}`, { value }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setSavedAt(new Date().toLocaleTimeString("cs-CZ"));
    },
  });

  if (!settingKey) {
    return (
      <div>
        <Header title="Globální nastavení" />
        <div className="p-6">
          <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            Neznámé nastavení: <code>{slug}</code>
          </div>
          <Link href="/admin">
            <Button variant="outline" size="sm" className="mt-4">
              <ArrowLeft className="h-3.5 w-3.5 mr-1" /> Zpět
            </Button>
          </Link>
        </div>
      </div>
    );
  }

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
      await saveMutation.mutateAsync(parsed);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Chyba ukládání");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setText(initialText);
    setError(null);
  }

  const isDirty = text !== initialText;

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
      <Header title={friendlyLabel} />
      <div className="p-6 space-y-4">
        {isLoading ? (
          <div className="flex items-center gap-2 text-gray-400 py-12 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" /> Načítám…
          </div>
        ) : !setting ? (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
            Setting <code>{settingKey}</code> není v DB. Spusť migraci 034.
          </div>
        ) : (
          <Card>
            <CardContent className="p-5 space-y-3">
              <div>
                <p className="text-xs text-gray-400 font-mono">{setting.key}</p>
                {setting.description && (
                  <p className="text-sm text-gray-700 mt-1">{setting.description}</p>
                )}
              </div>

              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={Math.min(text.split("\n").length + 1, 22)}
                className="w-full font-mono text-sm rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
        )}
      </div>
    </div>
  );
}
