"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Jednoduchý CSS-only tooltip založený na Tailwind group/group-hover.
 * Renderuje se nad/pod/vedle children při hoveru. Žádný JS, žádný portal.
 *
 * Použití:
 *   <Tooltip label="Upravit záznam">
 *     <button>...</button>
 *   </Tooltip>
 *
 * Pozn.: díky group-hover funguje i pro disabled buttony.
 * Také se zobrazuje při focusu (keyboard navigation).
 */
export function Tooltip({
  children,
  label,
  side = "top",
  className,
}: {
  children: ReactNode;
  label: string;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}) {
  return (
    <span className={cn("relative group inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded bg-gray-900 text-white text-xs font-medium px-2 py-1 shadow-md",
          "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-150",
          side === "top" && "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
          side === "bottom" && "top-full left-1/2 -translate-x-1/2 mt-1.5",
          side === "left" && "right-full top-1/2 -translate-y-1/2 mr-1.5",
          side === "right" && "left-full top-1/2 -translate-y-1/2 ml-1.5",
        )}
      >
        {label}
      </span>
    </span>
  );
}
