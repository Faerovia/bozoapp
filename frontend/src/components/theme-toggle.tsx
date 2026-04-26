"use client";

/**
 * Dark mode toggle — light / dark / system.
 *
 * Persistuje výběr v localStorage. Při SSR se použije system preference.
 * Třída `dark` se přidá na <html> elementu (Tailwind darkMode: 'class').
 */

import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

type Mode = "light" | "dark" | "system";

const STORAGE_KEY = "digitalozo_theme";

function applyTheme(mode: Mode) {
  if (typeof document === "undefined") return;
  const isDark = mode === "dark"
    || (mode === "system"
      && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", isDark);
}

function readMode(): Mode {
  if (typeof localStorage === "undefined") return "system";
  const saved = localStorage.getItem(STORAGE_KEY) as Mode | null;
  return saved ?? "system";
}

export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const m = readMode();
    setMode(m);
    applyTheme(m);

    // Reaguj na změnu system preference, pokud je aktivní mode=system
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (readMode() === "system") applyTheme("system");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  function set(m: Mode) {
    localStorage.setItem(STORAGE_KEY, m);
    setMode(m);
    applyTheme(m);
  }

  if (!mounted) {
    return <div className="w-[88px] h-[30px]" />;  // SSR placeholder
  }

  const Icon = mode === "dark" ? Moon : mode === "light" ? Sun : Monitor;

  return (
    <div className="inline-flex rounded-md border border-gray-300 dark:border-gray-700 overflow-hidden">
      {(["light", "system", "dark"] as Mode[]).map((m) => {
        const M = m === "dark" ? Moon : m === "light" ? Sun : Monitor;
        return (
          <button
            key={m}
            type="button"
            onClick={() => set(m)}
            className={cn(
              "px-2 py-1 text-xs transition-colors",
              mode === m
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-500 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700",
            )}
            title={m === "light" ? "Světlý" : m === "dark" ? "Tmavý" : "Dle systému"}
            aria-label={`${m} mode`}
          >
            <M className="h-3.5 w-3.5" />
          </button>
        );
      })}
      {/* Hidden Icon var pro keep-import-alive (a kdyby UI chtělo single-icon variantu) */}
      <span className="hidden">
        <Icon className="h-3.5 w-3.5" />
      </span>
    </div>
  );
}
