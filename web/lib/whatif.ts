import type { WhatIf, WhatIfRaw } from "./types";

const n = (v: unknown): number | null => (typeof v === "number" ? v : null);

function counts(c: Record<string, number> | undefined) {
  const o = c ?? {};
  return {
    under_restricted: n(o.models_under_restricted ?? o.models_under_nc_license),
    below_one: n(o.models_below_one),
    affected_total: n(o.affected_total),
  };
}

/** Maps either /api/what-if payload shape onto one. */
export function normalizeWhatIf(r: WhatIfRaw): WhatIf {
  const g = r.graphs;
  const family = Array.isArray(g) ? (g[0] ?? null) : (g?.family ?? null);
  const copy = Array.isArray(g) ? (g[1] ?? null) : (g?.copy ?? null);
  return {
    scenario: r.scenario,
    root: r.root ?? null,
    from_license: r.from_license ?? null,
    to_license: r.to_license ?? null,
    family_models: r.family_models,
    family_edges: n(r.family_edges),
    before: counts(r.before),
    after: counts(r.after),
    still_restricted_after: n(
      r.still_labelled_restricted_after ?? r.still_labelled_non_commercial_after ?? r.still_non_commercial_after,
    ),
    relabel_needed: r.relabel_needed ?? [],
    why: r.why ?? null,
    family_graph: family,
    copy_graph: copy,
    seconds: r.seconds ?? {},
    cached_family: Boolean(r.cached_family),
  };
}

/** "0.12 s" or "850 ms". */
export function secs(v: number | undefined): string | null {
  if (v == null) return null;
  return v < 1 ? `${Math.round(v * 1000)} ms` : `${v.toFixed(v < 10 ? 2 : 1)} s`;
}
