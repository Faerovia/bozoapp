"use client";

/**
 * SearchableSelect — dropdown s textovým hledáním na prvním řádku.
 *
 * Použití:
 *   <SearchableSelect
 *     options={employees.map(e => ({
 *       value: e.id,
 *       label: `${e.last_name} ${e.first_name}`,
 *       hint: e.personal_number ?? undefined,
 *     }))}
 *     value={selectedId}
 *     onChange={setSelectedId}
 *     placeholder="— vyber zaměstnance —"
 *   />
 *
 * Klávesové ovládání:
 *   ↑/↓ — navigace, Enter — výběr, Esc — zavřít
 *   Otvírá se kliknutím nebo focus + jakýkoli alfanumerický klíč.
 */

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, X, Search } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SearchableOption {
  value: string;
  label: string;
  /** Volitelný 2. řádek (např. osobní číslo, pozice). */
  hint?: string;
  /** Pokud true, řádek se zobrazí jako disabled (neselectable). */
  disabled?: boolean;
}

interface Props {
  options: SearchableOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Když false (default), vlastníci klíčových modifierů ignorují listenery. */
  required?: boolean;
  /** ID pro <Label htmlFor=...> binding. */
  id?: string;
  className?: string;
}

const TRIGGER_CLS = (open: boolean, disabled: boolean) => cn(
  "flex items-center justify-between w-full rounded-md border bg-white px-3 py-2 text-sm transition-colors",
  open
    ? "border-blue-500 ring-2 ring-blue-500/20"
    : "border-gray-300 hover:border-gray-400",
  disabled && "bg-gray-50 cursor-not-allowed opacity-60",
);

export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "— vyber —",
  disabled = false,
  required = false,
  id,
  className,
}: Props) {
  const generatedId = useId();
  const triggerId = id ?? generatedId;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = options.find((o) => o.value === value) ?? null;

  // Filter podle query (case-insensitive, match label OR hint)
  const filtered = !query.trim()
    ? options
    : options.filter((o) => {
        const q = query.toLowerCase();
        return (
          o.label.toLowerCase().includes(q) ||
          (o.hint?.toLowerCase().includes(q) ?? false)
        );
      });

  useEffect(() => {
    if (!open) return;
    setActiveIndex(0);
    // Focus search input po otevření
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // Zavři dropdown při kliknutí mimo
  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  function pick(opt: SearchableOption) {
    if (opt.disabled) return;
    onChange(opt.value);
    setOpen(false);
    setQuery("");
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      setQuery("");
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const opt = filtered[activeIndex];
      if (opt) pick(opt);
      return;
    }
  }

  return (
    <div ref={wrapperRef} className={cn("relative", className)}>
      <button
        id={triggerId}
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        className={TRIGGER_CLS(open, disabled)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cn("truncate text-left", !selected && "text-gray-400")}>
          {selected?.label || placeholder}
        </span>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {selected && !required && !disabled && (
            <span
              role="button"
              tabIndex={-1}
              onClick={(e) => {
                e.stopPropagation();
                onChange(null);
              }}
              className="rounded p-0.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100"
              aria-label="Vymazat výběr"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown
            className={cn(
              "h-4 w-4 text-gray-400 transition-transform",
              open && "rotate-180",
            )}
          />
        </div>
      </button>

      {open && (
        <div
          className="absolute z-50 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg max-h-72 overflow-hidden flex flex-col"
          role="listbox"
        >
          {/* Vyhledávací řádek na prvním místě */}
          <div className="border-b border-gray-100 px-2 py-2 bg-gray-50">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={handleKey}
                placeholder="Vyhledat…"
                className="w-full rounded-md border border-gray-200 bg-white pl-7 pr-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Seznam */}
          <div className="overflow-y-auto flex-1">
            {filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-gray-400">
                {query ? "Žádné výsledky" : "Žádné položky"}
              </div>
            ) : (
              <ul>
                {filtered.map((opt, i) => {
                  const isActive = i === activeIndex;
                  const isSelected = opt.value === value;
                  return (
                    <li key={opt.value}>
                      <button
                        type="button"
                        onClick={() => pick(opt)}
                        onMouseEnter={() => setActiveIndex(i)}
                        disabled={opt.disabled}
                        className={cn(
                          "w-full text-left px-3 py-2 text-sm flex items-start justify-between gap-2 transition-colors",
                          isActive && !opt.disabled && "bg-blue-50",
                          isSelected && "bg-blue-100 font-medium",
                          opt.disabled && "opacity-40 cursor-not-allowed",
                        )}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{opt.label}</span>
                          {opt.hint && (
                            <span className="block text-xs text-gray-500 truncate">
                              {opt.hint}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
