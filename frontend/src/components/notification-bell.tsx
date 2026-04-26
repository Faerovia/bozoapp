"use client";

/**
 * Bell ikona v headeru se sumarizací aktuálních upozornění z dashboard endpointu.
 *
 * Načítá `/dashboard` (cache 60s) a zobrazí počet:
 *  - expiring_trainings (≤30 dní, expired)
 *  - overdue_revisions
 *  - pending_risk_reviews
 *  - draft_accident_reports
 *
 * Dropdown ukazuje top 5 položek z upcoming_calendar.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Bell, AlertTriangle, GraduationCap, Wrench, ClipboardList, ShieldAlert,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CalendarItem {
  source: string;
  source_id: string;
  title: string;
  due_date: string;
  due_status: string;
  detail_url: string;
}

interface DashboardSummary {
  expiring_trainings: { id: string; title: string; valid_until: string | null; status: string }[];
  overdue_revisions: { id: string; title: string; next_revision_at: string | null }[];
  pending_risk_reviews: unknown[];
  draft_accident_reports: unknown[];
  upcoming_calendar: CalendarItem[];
}

const SOURCE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  training: GraduationCap,
  revision: Wrench,
  risk: ShieldAlert,
};

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString("cs-CZ");
}

function daysUntil(iso: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(iso);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / (24 * 60 * 60 * 1000));
}

function dueLabel(days: number): string {
  if (days < 0) return `po termínu ${Math.abs(days)} d.`;
  if (days === 0) return "dnes";
  if (days === 1) return "zítra";
  return `za ${days} d.`;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { data } = useQuery<DashboardSummary>({
    queryKey: ["notification-bell"],
    queryFn: () => api.get("/dashboard"),
    refetchInterval: 5 * 60 * 1000,  // 5 min poll
    staleTime: 60 * 1000,
    retry: false,
  });

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  const counts = data ? {
    trainings: data.expiring_trainings?.length ?? 0,
    revisions: data.overdue_revisions?.length ?? 0,
    risks: data.pending_risk_reviews?.length ?? 0,
    drafts: data.draft_accident_reports?.length ?? 0,
  } : { trainings: 0, revisions: 0, risks: 0, drafts: 0 };

  const total = counts.trainings + counts.revisions + counts.risks + counts.drafts;
  const calendar = (data?.upcoming_calendar ?? []).slice(0, 5);

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
        aria-label={`Upozornění: ${total}`}
      >
        <Bell className="h-5 w-5" />
        {total > 0 && (
          <span className={cn(
            "absolute -top-0.5 -right-0.5 inline-flex items-center justify-center",
            "rounded-full text-[10px] font-bold text-white px-1.5 min-w-[16px] h-[16px]",
            counts.revisions > 0 ? "bg-red-600" : "bg-blue-600",
          )}>
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 rounded-md border border-gray-200 bg-white shadow-lg overflow-hidden z-50">
          <div className="border-b border-gray-100 px-4 py-3 bg-gray-50">
            <p className="text-sm font-semibold text-gray-900">Upozornění</p>
            {total === 0 && (
              <p className="text-xs text-gray-500 mt-0.5">Vše v pořádku, nic nečeká.</p>
            )}
          </div>

          {total > 0 && (
            <div className="border-b border-gray-100 grid grid-cols-2 divide-x divide-gray-100">
              <Link
                href="/trainings"
                onClick={() => setOpen(false)}
                className="px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-xs text-gray-700"
              >
                <GraduationCap className="h-3.5 w-3.5 text-blue-600" />
                <span className="flex-1">Školení</span>
                <strong className="text-blue-700">{counts.trainings}</strong>
              </Link>
              <Link
                href="/revisions"
                onClick={() => setOpen(false)}
                className="px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-xs text-gray-700"
              >
                <Wrench className="h-3.5 w-3.5 text-red-600" />
                <span className="flex-1">Revize po termínu</span>
                <strong className="text-red-700">{counts.revisions}</strong>
              </Link>
              <Link
                href="/risks"
                onClick={() => setOpen(false)}
                className="px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-xs text-gray-700"
              >
                <ShieldAlert className="h-3.5 w-3.5 text-amber-600" />
                <span className="flex-1">Revize rizik</span>
                <strong className="text-amber-700">{counts.risks}</strong>
              </Link>
              <Link
                href="/accident-reports"
                onClick={() => setOpen(false)}
                className="px-3 py-2 hover:bg-gray-50 flex items-center gap-2 text-xs text-gray-700"
              >
                <ClipboardList className="h-3.5 w-3.5 text-gray-600" />
                <span className="flex-1">Úrazy — drafty</span>
                <strong className="text-gray-700">{counts.drafts}</strong>
              </Link>
            </div>
          )}

          {calendar.length > 0 && (
            <div className="max-h-80 overflow-y-auto">
              <p className="px-4 py-2 text-[10px] uppercase font-medium text-gray-500 bg-gray-50/50">
                Nejbližší termíny
              </p>
              <ul className="divide-y divide-gray-100">
                {calendar.map((it) => {
                  const Icon = SOURCE_ICONS[it.source] ?? AlertTriangle;
                  const days = daysUntil(it.due_date);
                  const overdue = days < 0;
                  return (
                    <li key={`${it.source}-${it.source_id}`}>
                      <Link
                        href={it.detail_url || "#"}
                        onClick={() => setOpen(false)}
                        className="flex items-start gap-2 px-4 py-2 hover:bg-gray-50"
                      >
                        <Icon className={cn(
                          "h-3.5 w-3.5 mt-0.5 shrink-0",
                          overdue ? "text-red-600" : "text-gray-400",
                        )} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-gray-800 truncate">{it.title}</p>
                          <p className="text-[10px] text-gray-500">
                            {fmtDate(it.due_date)} · <span className={overdue ? "text-red-600 font-medium" : ""}>{dueLabel(days)}</span>
                          </p>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <Link
            href="/dashboard"
            onClick={() => setOpen(false)}
            className="block border-t border-gray-100 px-4 py-2 text-xs text-blue-600 hover:bg-blue-50 text-center"
          >
            Otevřít dashboard →
          </Link>
        </div>
      )}
    </div>
  );
}
