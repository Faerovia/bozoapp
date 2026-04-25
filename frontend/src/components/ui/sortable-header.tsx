"use client";

import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import type { SortDir } from "@/lib/use-table-sort";
import { cn } from "@/lib/utils";

interface Props {
  sortKey: string;
  current: string | null;
  dir: SortDir;
  onSort: (key: string) => void;
  children: React.ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
}

export function SortableHeader({
  sortKey, current, dir, onSort, children, className, align = "left",
}: Props) {
  const active = current === sortKey;
  const Icon = !active ? ChevronsUpDown : (dir === "asc" ? ChevronUp : ChevronDown);

  return (
    <th
      className={cn(
        "py-3 px-4 font-medium text-gray-500 select-none",
        align === "left" && "text-left",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 group hover:text-gray-700 transition-colors",
          active && "text-gray-800",
        )}
      >
        {children}
        <Icon className={cn(
          "h-3 w-3 shrink-0",
          active ? "text-blue-600" : "text-gray-300 group-hover:text-gray-500"
        )} />
      </button>
    </th>
  );
}
