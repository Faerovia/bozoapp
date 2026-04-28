/**
 * Centrální query-key invalidace pro entity, které jsou sdílené napříč moduly
 * (provozovny, pracoviště, pozice).
 *
 * Historicky vznikly nekonzistentní queryKeys napříč moduly:
 *  - /workplaces:     ["positions"], ["positions", workplaceId]
 *  - /employees:      ["job-positions"]
 *  - /risks, /trainings, /documents, /oopp main: ["job-positions", ...]
 *  - /oopp positions tab: ["oopp-positions"]
 *  - /risk-overview:  ["risk-overview-positions"]
 *
 * Tyto helpery zajišťují, že invalidace v jednom modulu propíše update do všech
 * ostatních modulů, které entitu zobrazují.
 */
import type { QueryClient } from "@tanstack/react-query";

const POSITION_KEYS = [
  ["positions"],
  ["job-positions"],
  ["oopp-positions"],
  ["risk-overview-positions"],
] as const;

const WORKPLACE_KEYS = [["workplaces"]] as const;
const PLANT_KEYS = [["plants"]] as const;

export function invalidatePositions(qc: QueryClient): void {
  for (const key of POSITION_KEYS) {
    qc.invalidateQueries({ queryKey: key });
  }
}

export function invalidateWorkplaces(qc: QueryClient): void {
  for (const key of WORKPLACE_KEYS) {
    qc.invalidateQueries({ queryKey: key });
  }
  // Workplace mutace mohou ovlivnit i pozice (cascade), invalidate i ty
  invalidatePositions(qc);
}

export function invalidatePlants(qc: QueryClient): void {
  for (const key of PLANT_KEYS) {
    qc.invalidateQueries({ queryKey: key });
  }
  invalidateWorkplaces(qc);
}
