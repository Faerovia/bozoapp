"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
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
  Briefcase,
  FileText,
  ShieldAlert,
  Crown,
  ArrowLeft,
  Clock,
  GitBranch,
  Timer,
  BookOpen,
  BookOpenCheck,
  ClipboardCheck,
  Receipt,
  Bell,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { UserResponse } from "@/types/api";
import { ClientSwitcher } from "./client-switcher";
import { ThemeToggle } from "@/components/theme-toggle";

// ── Role model (sjednocené s backend/permissions.py) ─────────────────────────
type Role =
  | "admin"
  | "ozo"
  | "hr_manager"
  | "lead_worker"
  | "equipment_responsible"
  | "employee";

// Tenant-level "managers" = plný přístup v tenantu (OZO + HR)
const MANAGERS: Role[] = ["ozo", "hr_manager"];
// Všechny tenant role (employee + responsible + lead + managers)
const ALL_TENANT: Role[] = ["ozo", "hr_manager", "lead_worker", "equipment_responsible", "employee"];

interface NavItem {
  href: string;
  // Label může být role-aware (employee vidí "Školící centrum" místo "Školení")
  label: string | ((role: Role) => string);
  icon: React.ComponentType<{ className?: string }>;
  roles: Role[];
}

// Pořadí + role per spec (BOZP/PO SaaS multi-tenant):
//  1. Moji klienti           — jen OZO (a admin)
//  2. Dashboard              — OZO + HR
//  3. Zaměstnanci            — OZO + HR
//  4. Lékařské prohlídky     — OZO + HR
//  5. OOPP                   — OZO + HR + lead_worker
//  6. Pracovní úrazy         — OZO + HR + lead_worker
//  7. Školení                — OZO + HR (admin pohled — správa šablon)
//  8. Školící centrum        — všechny tenant role (absolvování přiřazených)
//  9. Revize                 — OZO + HR + equipment_responsible
// 10. Pravidelné kontroly    — všichni (zobrazí se jen co mají přiřazené)
// 11. Provozní deníky        — všichni
// 12. Provozovny, pracoviště — OZO + HR
// 13. Úroveň rizik           — OZO + HR
// 14. Dokumenty              — OZO + HR
// 15. Fakturace              — OZO + HR
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
    href: "/medical-exams",
    label: "Lékařské prohlídky",
    icon: Stethoscope,
    roles: MANAGERS,
  },
  {
    href: "/oopp",
    label: "OOPP",
    icon: HardHat,
    roles: ["ozo", "hr_manager", "lead_worker"],
  },
  {
    href: "/accident-reports",
    label: "Pracovní úrazy",
    icon: AlertTriangle,
    roles: ["ozo", "hr_manager", "lead_worker"],
  },
  {
    href: "/trainings",
    label: "Školení",
    icon: GraduationCap,
    roles: MANAGERS,
  },
  {
    // Stejná stránka /trainings s tabem "Mé přiřazené" — absolvování školení.
    // Zobrazuje se VŠEM rolím včetně OZO/HR (i management se musí proškolit).
    href: "/trainings?view=my",
    label: "Školící centrum",
    icon: BookOpen,
    roles: ALL_TENANT,
  },
  {
    href: "/revisions",
    label: "Revize",
    icon: Wrench,
    roles: ["ozo", "hr_manager", "equipment_responsible"],
  },
  {
    href: "/periodic-checks",
    label: "Pravidelné kontroly",
    icon: ClipboardCheck,
    roles: ALL_TENANT,
  },
  {
    href: "/operating-logs",
    label: "Provozní deníky",
    icon: BookOpenCheck,
    roles: ALL_TENANT,
  },
  {
    href: "/workplaces",
    label: "Provozovny, pracoviště, pozice",
    icon: Building2,
    roles: MANAGERS,
  },
  {
    href: "/risk-overview",
    label: "Úroveň rizik na pracovištích",
    icon: ShieldAlert,
    roles: MANAGERS,
  },
  {
    href: "/documents",
    label: "Dokumenty",
    icon: FileText,
    roles: MANAGERS,
  },
  {
    href: "/billing",
    label: "Fakturace",
    icon: Receipt,
    roles: MANAGERS,
  },
];


// Položky pro platform admin sekci (/admin/*).
// Když je admin v této sekci, sidebar nahradí běžné moduly těmito.
interface AdminNavItem {
  href: string;
  label: string;
  icon: typeof Crown;
  exact?: boolean;
}

const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  {
    href: "/admin",
    label: "Zákazníci",
    icon: Users,
    exact: true,
  },
  {
    href: "/admin/trainings",
    label: "Globální školení",
    icon: BookOpen,
  },
  {
    href: "/admin/invoices",
    label: "Faktury",
    icon: Receipt,
  },
  {
    href: "/admin/settings/invoice-issuer",
    label: "Fakturační údaje firmy",
    icon: Building2,
  },
  {
    href: "/admin/settings/reminders",
    label: "Email reminders",
    icon: Bell,
  },
  // Skupina: lékařské prohlídky — každé setting jako samostatný item
  {
    href: "/admin/settings/medical-exam-periodicity",
    label: "Lhůty prohlídek (kategorie + věk)",
    icon: Clock,
  },
  {
    href: "/admin/settings/factor-to-specialties",
    label: "Faktor → odborné prohlídky",
    icon: GitBranch,
  },
  {
    href: "/admin/settings/specialty-periodicity",
    label: "Periodicita odborných prohlídek",
    icon: Clock,
  },
  {
    href: "/admin/settings/expiring-warning",
    label: "Varování o expiraci prohlídek",
    icon: AlertTriangle,
  },
  {
    href: "/admin/settings/auto-throttle",
    label: "Throttle auto-generace",
    icon: Timer,
  },
  {
    href: "/admin/audit",
    label: "Audit log",
    icon: Activity,
  },
];


export function Sidebar() {
  // useSearchParams() vyžaduje Suspense pro Next.js prerender (statická
  // generace by jinak selhala). Wrapper drží zbytek sidebaru, vnitřní
  // komponenta čte query string.
  return (
    <Suspense fallback={<SidebarShell />}>
      <SidebarInner />
    </Suspense>
  );
}

// Loading skeleton — minimalistická kostra (žádné useSearchParams).
function SidebarShell() {
  return (
    <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-14 items-center border-b border-gray-200 px-5">
        <span className="text-lg font-bold text-blue-600">DigitalOZO</span>
      </div>
      <div className="flex-1 px-3 py-4 text-xs text-gray-300">Načítám…</div>
    </aside>
  );
}

function SidebarInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentView = searchParams.get("view");

  const { data: user } = useQuery<UserResponse>({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  const role = (user?.role as Role | undefined) ?? null;
  const isPlatformAdmin = user?.is_platform_admin === true;
  const isOnAdminPath = pathname.startsWith("/admin");

  // Tři režimy zobrazení sidebaru:
  // 1) Platform admin v /admin sekci → ADMIN_NAV_ITEMS (bez tenant modulů)
  // 2) Platform admin mimo /admin (impersonate) → všechny tenant moduly + zpět odkaz
  // 3) Běžný tenant user → moduly podle role
  const adminMode = isPlatformAdmin && isOnAdminPath;
  const visible = adminMode
    ? []   // unused — renderujeme z ADMIN_NAV_ITEMS
    : isPlatformAdmin
      ? NAV_ITEMS
      : role
        ? NAV_ITEMS.filter((item) => item.roles.includes(role))
        : [];

  return (
    <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-gray-200 px-5">
        <span className="text-lg font-bold text-blue-600">DigitalOZO</span>
        <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-600">
          beta
        </span>
      </div>

      {/* Client switcher (jen pro OZO multi-client; ne v admin sekci) */}
      {!adminMode && <ClientSwitcher />}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {/* ── Admin mode: jen admin položky + heading ─────────────────────── */}
          {adminMode && (
            <>
              <li className="px-3 py-2 mb-2 rounded-md bg-amber-50 text-amber-700">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Crown className="h-4 w-4 shrink-0" />
                  Platform admin
                </div>
              </li>
              {ADMIN_NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => {
                const active = exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        active
                          ? "bg-amber-100 text-amber-800"
                          : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {label}
                    </Link>
                  </li>
                );
              })}
            </>
          )}

          {/* ── Tenant mode (impersonate nebo běžný user) ───────────────────── */}
          {!adminMode && isPlatformAdmin && (
            <li className="mb-3 pb-3 border-b border-gray-100">
              <Link
                href="/admin"
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
              >
                <ArrowLeft className="h-4 w-4 shrink-0" />
                Zpět do Platform admin
              </Link>
            </li>
          )}
          {!adminMode && visible.map(({ href, label, icon: Icon }) => {
            // Href může mít query string (např. "/trainings?view=my").
            // Active state musí matchnout pathname + view param zvlášť.
            const [hrefPath, hrefQuery] = href.split("?");
            const targetView = hrefQuery
              ? new URLSearchParams(hrefQuery).get("view")
              : null;
            const pathMatches =
              pathname === hrefPath || pathname.startsWith(hrefPath + "/");
            const active = pathMatches && currentView === targetView;
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

      {/* Theme toggle (dříve zde bylo "Odhlásit se" — to je teď v headeru). */}
      <div className="border-t border-gray-200 dark:border-gray-700 p-3 flex items-center justify-between">
        <span className="text-xs text-gray-500 dark:text-gray-400">Vzhled</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
