"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  GraduationCap,
  Wrench,
  AlertTriangle,
  HardHat,
  Building2,
  Stethoscope,
  Briefcase,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/dashboard",         label: "Dashboard",            icon: LayoutDashboard },
  { href: "/employees",         label: "Zaměstnanci",          icon: Users },
  { href: "/trainings",         label: "Školení",              icon: GraduationCap },
  { href: "/revisions",         label: "Revize",               icon: Wrench },
  { href: "/accident-reports",  label: "Pracovní úrazy",       icon: AlertTriangle },
  { href: "/oopp",              label: "OOPP",                 icon: HardHat },
  { href: "/workplaces",        label: "Pracoviště",           icon: Building2 },
  { href: "/medical-exams",     label: "Lékařské prohlídky",   icon: Stethoscope },
  { href: "/job-positions",     label: "Pracovní pozice",      icon: Briefcase },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-gray-200 px-5">
        <span className="text-lg font-bold text-blue-600">BOZOapp</span>
        <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-600">
          beta
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
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
                  {label}
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
