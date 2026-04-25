"use client";

/**
 * Generický hook pro sortování tabulek.
 *
 * Použití:
 *   const { sortedItems, sortKey, sortDir, toggleSort } = useTableSort(items, "name");
 *   <SortableHeader sortKey="name" current={sortKey} dir={sortDir} onSort={toggleSort}>
 *     Jméno
 *   </SortableHeader>
 *
 * Podporuje vnořené klíče typu "plant.name" přes jednoduchou tečkovou notaci.
 */

import { useMemo, useState } from "react";

export type SortDir = "asc" | "desc";

function getNested<T>(obj: T, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object" && key in acc) {
      return (acc as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

function compare(a: unknown, b: unknown): number {
  // null/undefined → na konec při asc (a před při desc)
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  // Bool: false → 0, true → 1
  if (typeof a === "boolean") a = a ? 1 : 0;
  if (typeof b === "boolean") b = b ? 1 : 0;

  // Datum (ISO string) — porovnej jako string fungovalo by, ale safer
  // necháme string compare na ISO strings
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "cs", { numeric: true, sensitivity: "base" });
}

export function useTableSort<T>(
  items: T[],
  defaultKey: string | null = null,
  defaultDir: SortDir = "asc",
) {
  const [sortKey, setSortKey] = useState<string | null>(defaultKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultDir);

  const sortedItems = useMemo(() => {
    if (!sortKey) return items;
    const sorted = [...items].sort((a, b) => {
      const va = getNested(a, sortKey);
      const vb = getNested(b, sortKey);
      const cmp = compare(va, vb);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [items, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey === key) {
      // ASC → DESC → off
      if (sortDir === "asc") setSortDir("desc");
      else { setSortKey(null); setSortDir("asc"); }
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return { sortedItems, sortKey, sortDir, toggleSort };
}
