"use client";

/**
 * Onboarding checklist — sticky panel na dashboardu pro nové zákazníky.
 * Skryje se pokud onboarding.completed nebo onboarding.dismissed.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2, Circle, ChevronDown, ChevronUp, Sparkles, X,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface ProgressItem {
  key: string;
  label: string;
  done: boolean;
  href: string | null;
}

interface ProgressResponse {
  items: ProgressItem[];
  done_count: number;
  total_count: number;
  percent: number;
  step1_completed: boolean;
  can_finish: boolean;
  completed: boolean;
  dismissed: boolean;
}

export function OnboardingChecklist() {
  const qc = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);

  const { data, isLoading } = useQuery<ProgressResponse>({
    queryKey: ["onboarding-progress"],
    queryFn: () => api.get("/onboarding/progress"),
    refetchInterval: 60_000,
  });

  const finishMutation = useMutation({
    mutationFn: () => api.post("/onboarding/finish"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-progress"] }),
  });

  const dismissMutation = useMutation({
    mutationFn: () => api.post("/onboarding/dismiss"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-progress"] }),
  });

  if (isLoading || !data) return null;
  if (data.completed || data.dismissed) return null;

  return (
    <div className="rounded-lg border border-blue-200 bg-gradient-to-br from-blue-50 to-white p-4 shadow-sm">
      {/* Hlavička */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="rounded-md bg-blue-600 p-1.5 text-white">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              Pojďme dát aplikaci dohromady
            </h3>
            <p className="text-xs text-gray-600">
              {data.done_count}/{data.total_count} hotových · {data.percent} %
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {data.can_finish && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => finishMutation.mutate()}
              loading={finishMutation.isPending}
            >
              Mám hotovo
            </Button>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-100"
            aria-label={collapsed ? "Rozbalit" : "Sbalit"}
          >
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
          <button
            onClick={() => {
              if (confirm("Skrýt onboarding navždy? Můžeš ho obnovit přes podporu."))
                dismissMutation.mutate();
            }}
            className="rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50"
            aria-label="Skrýt"
            title="Skrýt navždy"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-2 w-full rounded-full bg-blue-100 overflow-hidden">
        <div
          className="h-full bg-blue-600 transition-all"
          style={{ width: `${data.percent}%` }}
        />
      </div>

      {/* Checklist */}
      {!collapsed && (
        <ul className="mt-4 space-y-1.5">
          {data.items.map((item) => (
            <li key={item.key}>
              {item.href && !item.done ? (
                <Link
                  href={item.href}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-blue-100"
                >
                  <Circle className="h-4 w-4 text-gray-400 shrink-0" />
                  <span className="text-gray-700">{item.label}</span>
                  <span className="ml-auto text-xs text-blue-600">→ Pokračovat</span>
                </Link>
              ) : (
                <div className="flex items-center gap-2 px-2 py-1.5 text-sm">
                  {item.done ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-gray-400 shrink-0" />
                  )}
                  <span className={item.done ? "text-gray-400 line-through" : "text-gray-700"}>
                    {item.label}
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
