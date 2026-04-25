"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Users,
  GraduationCap,
  Wrench,
  AlertTriangle,
  HardHat,
  Building2,
  Stethoscope,
  LogOut,
  Briefcase,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api, logout } from "@/lib/api";
import type { UserResponse } from "@/types/api";
import { ClientSwitcher } from "./client-switcher";

// ── Role model (sjednocené s backend/permissions.py) ─────────────────────────
type Role =
  | "admin"
  | "ozo"
  | "hr_manager"
  | "equipment_responsible"
  | "employee";

// Tenant-level "managers" = plný přístup v tenantu (OZO + HR)
const MANAGERS: Role[] = ["ozo", "hr_manager"];
// Všechny tenant role (employee + responsible + managers)
const ALL_TENANT: Role[] = ["ozo", "hr_manager", "equipment_responsible", "employee"];

interface NavItem {
  href: string;
  // Label může být role-aware (employee vidí "Školící centrum" místo "Školení")
  label: string | ((role: Role) => string);
  icon: React.ComponentType<{ className?: string }>;
  roles: Role[];
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/my-clients",
    label: "Moji klienti",
    icon: Briefcase,
    roles: ["admin", "ozo"],
  },
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    roles: MANAGERS,
  },
  {
    href: "/employees",
    label: "Zaměstnanci",
    icon: Users,
    roles: MANAGERS,
  },
  {
    href: "/trainings",
    // OZO/HR spravují školení, zaměstnanec/equipment_responsible je absolvuje
    label: (role) =>
      role === "employee" || role === "equipment_responsible"
        ? "Školící centrum"
        : "Školení",
    icon: GraduationCap,
    roles: ALL_TENANT,
  },
  {
    href: "/revisions",
    label: "Revize",
    icon: Wrench,
    // OZO/HR + equipment_responsible (správa svých vyhrazených zařízení)
    roles: ["ozo", "hr_manager", "equipment_responsible"],
  },
  {
    href: "/accident-reports",
    label: "Pracovní úrazy",
    icon: AlertTriangle,
    roles: MANAGERS,
  },
  {
    href: "/oopp",
    label: "OOPP",
    icon: HardHat,
    roles: ALL_TENANT,
  },
  {
    href: "/workplaces",
    label: "Provozovny, pracoviště, pozice",
    icon: Building2,
    roles: MANAGERS,
  },
  {
    href: "/medical-exams",
    label: "Lékařské prohlídky",
    icon: Stethoscope,
    roles: ALL_TENANT,
  },
];


export function Sidebar() {
  const pathname = usePathname();

  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  const role = (user?.role as Role | undefined) ?? null;
  const visible = role
    ? NAV_ITEMS.filter((item) => item.roles.includes(role))
    : [];

  return (
    <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-gray-200 px-5">
        <span className="text-lg font-bold text-blue-600">BOZOapp</span>
        <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-600">
          beta
        </span>
      </div>

      {/* Client switcher (jen pro OZO multi-client) */}
      <ClientSwitcher />

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {visible.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            const labelText = typeof label === "function" ? label(role!) : label;
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-blue-50 text-blue-700"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {labelText}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Logout */}
      <div className="border-t border-gray-200 p-3">
        <button
          onClick={() => logout()}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Odhlásit se
        </button>
      </div>
    </aside>
  );
}
