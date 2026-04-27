"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, LogOut } from "lucide-react";
import { api, logout } from "@/lib/api";
import type { UserResponse } from "@/types/api";
import { NotificationBell } from "@/components/notification-bell";
import { ChangePasswordModal } from "@/components/change-password-modal";

interface HeaderProps {
  title: string;
  actions?: React.ReactNode;
}

export function Header({ title, actions }: HeaderProps) {
  const [pwdOpen, setPwdOpen] = useState(false);

  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  // Bell zobrazujeme jen pro tenant managers (OZO/HR) — endpoint /dashboard
  // vyžaduje require_role("ozo", "hr_manager")
  const showBell = user && (user.role === "ozo" || user.role === "hr_manager");

  return (
    <>
      <header className="flex h-14 items-center justify-between border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6">
        <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h1>
        <div className="flex items-center gap-2">
          {actions}
          {showBell && <NotificationBell />}

          {/* Změna hesla — vedle notifikací (dle specu) */}
          <button
            type="button"
            onClick={() => setPwdOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Změnit heslo"
          >
            <KeyRound className="h-3.5 w-3.5" />
            Změna hesla
          </button>

          {/* Odhlásit — vedle notifikací (dle specu) */}
          <button
            type="button"
            onClick={() => logout()}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Odhlásit se"
          >
            <LogOut className="h-3.5 w-3.5" />
            Odhlásit
          </button>

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

      <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
    </>
  );
}
