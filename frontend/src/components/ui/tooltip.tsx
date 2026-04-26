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
  wide = false,
  className,
}: {
  children: ReactNode;
  label: string;
  side?: "top" | "bottom" | "left" | "right";
  /**
   * Pro delší texty (legislativa, helptext) — povolí zalomení na více řádků
   * s max-width 20rem. Default: false (single-line nowrap pro krátké tooltipy).
   */
  wide?: boolean;
  className?: string;
}) {
  // Heuristika: pokud label > 60 znaků, automaticky zapni wide aby nepřetékal
  const useWide = wide || label.length > 60;
  return (
    <span className={cn("relative group inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 rounded bg-gray-900 text-white text-xs font-medium px-2 py-1 shadow-md",
          useWide
            ? "whitespace-normal w-72 leading-snug"
            : "whitespace-nowrap",
          "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-150",
          // Wide tooltipy se neumísťují centrovaně (přetekly by ven z dialogu),
          // ale s pravým okrajem zarovnaným s parent ikonou.
          !useWide && side === "top" && "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
          !useWide && side === "bottom" && "top-full left-1/2 -translate-x-1/2 mt-1.5",
          useWide && side === "top" && "bottom-full right-0 mb-1.5",
          useWide && side === "bottom" && "top-full right-0 mt-1.5",
          side === "left" && "right-full top-1/2 -translate-y-1/2 mr-1.5",
          side === "right" && "left-full top-1/2 -translate-y-1/2 ml-1.5",
        )}
      >
        {label}
      </span>
    </span>
  );
}
