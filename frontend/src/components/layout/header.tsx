"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { UserResponse } from "@/types/api";
import { NotificationBell } from "@/components/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";

interface HeaderProps {
  title: string;
  actions?: React.ReactNode;
}

export function Header({ title, actions }: HeaderProps) {
  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  // Bell zobrazujeme jen pro tenant managers (OZO/HR) — endpoint /dashboard
  // vyžaduje require_role("ozo", "hr_manager")
  const showBell = user && (user.role === "ozo" || user.role === "hr_manager");

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6">
      <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h1>
      <div className="flex items-center gap-3">
        {actions}
        <ThemeToggle />
        {showBell && <NotificationBell />}
        {user && (
          <div className="flex items-center gap-2 pl-3 border-l border-gray-200 dark:border-gray-700">
            <span className="text-sm text-gray-500 dark:text-gray-400">{user.email}</span>
            <span className="rounded-full bg-blue-100 dark:bg-blue-900/40 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300 uppercase">
              {user.role}
            </span>
          </div>
        )}
      </div>
    </header>
  );
}
