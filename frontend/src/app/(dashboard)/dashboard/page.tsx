"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DashboardResponse, CalendarItem, UserResponse } from "@/types/api";
import { Header } from "@/components/layout/header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import {
  AlertTriangle,
  GraduationCap,
  Wrench,
  FileText,
  Stethoscope,
  CalendarClock,
  TrendingUp,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { OnboardingChecklist } from "@/components/onboarding-checklist";
import { OnboardingWizard } from "@/components/onboarding-wizard";

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ElementType;
  color: "red" | "amber" | "blue" | "orange";
  description: string;
}

function StatCard({ title, value, icon: Icon, color, description }: StatCardProps) {
  const colors = {
    red:    { bg: "bg-red-50",    text: "text-red-700",    icon: "text-red-500",    ring: "ring-red-100" },
    amber:  { bg: "bg-amber-50",  text: "text-amber-700",  icon: "text-amber-500",  ring: "ring-amber-100" },
    blue:   { bg: "bg-blue-50",   text: "text-blue-700",   icon: "text-blue-500",   ring: "ring-blue-100" },
    orange: { bg: "bg-orange-50", text: "text-orange-700", icon: "text-orange-500", ring: "ring-orange-100" },
  };
  const c = colors[color];

  return (
    <Card className={cn("transition-shadow hover:shadow-md", value > 0 && c.bg)}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-500">{title}</p>
            <p className={cn("text-3xl font-bold", value > 0 ? c.text : "text-gray-900")}>
              {value}
            </p>
            <p className="text-xs text-gray-400">{description}</p>
          </div>
          <div className={cn("rounded-full p-2 ring-2", value > 0 ? c.ring : "ring-gray-100")}>
            <Icon className={cn("h-5 w-5", value > 0 ? c.icon : "text-gray-400")} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Calendar table ────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<CalendarItem["source"], string> = {
  revision:     "Revize",
  risk:         "Riziko",
  training:     "Školení",
  medical_exam: "Prohlídka",
};

const SOURCE_COLORS: Record<CalendarItem["source"], string> = {
  revision:     "bg-purple-100 text-purple-700",
  risk:         "bg-rose-100 text-rose-700",
  training:     "bg-blue-100 text-blue-700",
  medical_exam: "bg-teal-100 text-teal-700",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("cs-CZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function CalendarTable({ items }: { items: CalendarItem[] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <CalendarClock className="h-10 w-10 mb-3 opacity-50" />
        <p className="text-sm">Žádné blížící se termíny v následujících 30 dnech</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="text-left py-3 px-4 font-medium text-gray-500">Název</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Typ</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Termín</th>
            <th className="text-left py-3 px-4 font-medium text-gray-500">Stav</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {items.map((item) => (
            <tr key={`${item.source}-${item.source_id}`} className="hover:bg-gray-50 transition-colors">
              <td className="py-3 px-4 font-medium text-gray-900">{item.title}</td>
              <td className="py-3 px-4">
                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", SOURCE_COLORS[item.source])}>
                  {SOURCE_LABELS[item.source]}
                </span>
              </td>
              <td className="py-3 px-4 text-gray-600">{formatDate(item.due_date)}</td>
              <td className="py-3 px-4">
                {item.due_status === "overdue" ? (
                  <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                    <AlertTriangle className="h-3 w-3" />
                    Po termínu
                  </span>
                ) : (
                  <span className="text-amber-600 text-xs font-medium">Blíží se</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Dashboard page ────────────────────────────────────────────────────────────

// Role povolené na dashboard (zbytek je přesměrován na svou landing stránku).
const DASHBOARD_ROLES = ["ozo", "hr_manager", "admin"];

// Kam přesměrovat role, které dashboard nevidí.
const ROLE_LANDING: Record<string, string> = {
  employee: "/trainings",
  equipment_responsible: "/revisions",
};

export default function DashboardPage() {
  const router = useRouter();

  // Role guard — pokud user nemá přístup na dashboard, přesměruj na jeho landing.
  const { data: me } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  const allowed = me ? DASHBOARD_ROLES.includes(me.role) : null;

  useEffect(() => {
    if (me && !DASHBOARD_ROLES.includes(me.role)) {
      router.replace(ROLE_LANDING[me.role] ?? "/trainings");
    }
  }, [me, router]);

  const { data, isLoading, isError } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => api.get("/dashboard"),
    refetchInterval: 5 * 60 * 1000,
    // Nedotaž se na /dashboard dokud neznáme roli nebo pokud není povolená
    // (jinak by employee vygeneroval 403 zbytečně).
    enabled: allowed === true,
  });

  // Dokud nevíme roli nebo jsme v redirectu, nerenderuj nic
  if (!me || allowed === false) {
    return (
      <div className="p-6 text-sm text-gray-400">Načítám…</div>
    );
  }

  return (
    <div>
      <Header title="Dashboard" />
      <OnboardingWizard />

      <div className="p-6 space-y-6">
        <OnboardingChecklist />
        {/* Stat cards */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-5 h-24 bg-gray-100 rounded-lg" />
              </Card>
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            Nepodařilo se načíst data. Zkuste obnovit stránku.
          </div>
        ) : data ? (
          <>
            {(data.workplaces_without_category ?? 0) > 0 && (
              <Link href="/risk-overview" className="block">
                <div className="rounded-lg bg-red-50 border border-red-300 p-4 flex items-center gap-3 hover:bg-red-100 transition-colors cursor-pointer">
                  <ShieldAlert className="h-6 w-6 text-red-600 shrink-0" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-red-800">
                      Pracoviště bez určené kategorie rizik: {data.workplaces_without_category}
                    </p>
                    <p className="text-xs text-red-700">
                      Každé pracoviště musí mít určenou kategorii rizik (RFA).
                      Klikněte pro přejití do modulu Úroveň rizik na pracovištích.
                    </p>
                  </div>
                </div>
              </Link>
            )}

          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <StatCard
              title="Čekající revize rizik"
              value={data.pending_risk_reviews}
              icon={AlertTriangle}
              color="red"
              description="Finalizované úrazy bez revize"
            />
            <StatCard
              title="Expirující školení"
              value={data.expiring_trainings}
              icon={GraduationCap}
              color="amber"
              description="Vyprší do 30 dnů"
            />
            <StatCard
              title="Prošlé revize"
              value={data.overdue_revisions}
              icon={Wrench}
              color="red"
              description="Po termínu revize"
            />
            <StatCard
              title="Rozpracované záznamy"
              value={data.draft_accident_reports}
              icon={FileText}
              color="orange"
              description="Úrazy ve stavu draft"
            />
            <StatCard
              title="Prohlídky – pozor"
              value={data.expiring_medical_exams}
              icon={Stethoscope}
              color="amber"
              description="Vyprší do 60 dnů"
            />
          </div>
          </>
        ) : null}

        {/* Calendar */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-gray-400" />
              <CardTitle>Nadcházející termíny</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-10 rounded bg-gray-100 animate-pulse" />
                ))}
              </div>
            ) : (
              <CalendarTable items={data?.upcoming_calendar ?? []} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
