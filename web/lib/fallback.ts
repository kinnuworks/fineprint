// Saved API responses for the hero models, written by scripts/refresh-fallback.mjs.
// Used only when the FinePrint API cannot be reached.
import type {
  Descendants,
  LoadBearing,
  ReadCardResult,
  RelicensePoints,
  WhatIfRaw,
  Report,
  Stats,
  Substitutes,
  Use,
} from "./types";
import bundle from "../public/fallback/bundle.json";
import { normalizeWhatIf } from "./whatif";

interface SavedModel {
  report?: Report;
  report_noncommercial?: Report;
  nograph?: Report;
  nograph_noncommercial?: Report;
  descendants?: Descendants;
  substitutes?: Substitutes;
  readcard?: ReadCardResult;
}

const B = bundle as unknown as {
  saved_at: string;
  stats: Stats;
  load_bearing: LoadBearing;
  relicense_points: RelicensePoints;
  what_if?: WhatIfRaw;
  models: Record<string, SavedModel>;
};

export const savedAt = B.saved_at;
export const savedStats = B.stats;
export const savedLoadBearing = B.load_bearing;
export const savedRelicensePoints = B.relicense_points;
export const savedWhatIf = B.what_if ? normalizeWhatIf(B.what_if) : null;
export const savedIds = Object.keys(B.models);

export function savedReport(id: string, graph: boolean, use: Use = "commercial"): Report | null {
  const m = B.models[id];
  if (!m) return null;
  if (graph) return (use === "noncommercial" ? m.report_noncommercial : m.report) ?? null;
  return (use === "noncommercial" ? m.nograph_noncommercial : m.nograph) ?? null;
}

export const savedDescendants = (id: string): Descendants | null => B.models[id]?.descendants ?? null;
export const savedSubstitutes = (id: string): Substitutes | null => B.models[id]?.substitutes ?? null;
export const savedReadCard = (id: string): ReadCardResult | null => B.models[id]?.readcard ?? null;
