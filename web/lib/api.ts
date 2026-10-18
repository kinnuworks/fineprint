import type {
  Descendants,
  LoadBearing,
  ReadCardResult,
  RelicensePoints,
  Report,
  SearchHit,
  Source,
  Stats,
  Substitutes,
  Use,
  WhatIf,
} from "./types";
import {
  savedDescendants,
  savedLoadBearing,
  savedReadCard,
  savedRelicensePoints,
  savedReport,
  savedStats,
  savedSubstitutes,
  savedWhatIf,
} from "./fallback";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/+$/, "");

/** Org rulesets are FalkorDB graphs named org:<slug>. */
export const RULESET_RE = /^[a-z0-9-]{3,40}$/;
export const DEMO_RULESET = "acme-legal";

/** Encodes a model id ("org/name" or "name") as URL path segments. */
export function idPath(id: string): string {
  return id.split("/").map(encodeURIComponent).join("/");
}

export class ApiDown extends Error {}
export class NotFound extends Error {}

async function getJson<T>(path: string, timeoutMs: number, revalidate?: number): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const init: RequestInit & { next?: { revalidate: number } } = { signal: ctrl.signal };
    if (typeof window === "undefined" && revalidate !== undefined) init.next = { revalidate };
    const res = await fetch(`${API_BASE}${path}`, init);
    if (res.status === 404) throw new NotFound(path);
    if (!res.ok) throw new ApiDown(`${res.status} ${path}`);
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof NotFound) throw err;
    throw new ApiDown(String(err));
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchModelCount(): Promise<number | null> {
  try {
    const h = await getJson<{ ok: boolean; models: number }>("/api/health", 4000, 3600);
    return h.models;
  } catch {
    return null;
  }
}

export async function fetchStats(): Promise<{ data: Stats; source: Source }> {
  try {
    return { data: await getJson<Stats>("/api/stats", 5000, 3600), source: "live" };
  } catch {
    return { data: savedStats, source: "saved" };
  }
}

/**
 * Fetches a report. Falls back to the saved copy for hero models when the API
 * cannot be reached. Returns null data when the API is down and no copy exists.
 */
export async function fetchReport(
  id: string,
  graph: boolean,
  use: Use = "commercial",
  ruleset = "",
): Promise<{ data: Report | null; source: Source | "down" }> {
  try {
    const rs = ruleset ? `&ruleset=${encodeURIComponent(ruleset)}` : "";
    const data = await getJson<Report>(`/api/report/${idPath(id)}?graph=${graph}&use=${use}${rs}`, 20000, 60);
    return { data, source: "live" };
  } catch {
    const saved = savedReport(id, graph, use);
    return saved ? { data: saved, source: "saved" } : { data: null, source: "down" };
  }
}

export async function fetchLoadBearing(k = 10): Promise<{ data: LoadBearing; source: Source }> {
  try {
    return { data: await getJson<LoadBearing>(`/api/load-bearing?k=${k}`, 15000, 3600), source: "live" };
  } catch {
    return { data: savedLoadBearing, source: "saved" };
  }
}

export async function fetchWhatIf(): Promise<WhatIf | null> {
  try {
    return await getJson<WhatIf>("/api/what-if", 15000, 3600);
  } catch {
    return savedWhatIf;
  }
}

export async function fetchRelicensePoints(k = 10): Promise<{ data: RelicensePoints; source: Source }> {
  try {
    return { data: await getJson<RelicensePoints>(`/api/relicense-points?k=${k}`, 40000, 3600), source: "live" };
  } catch {
    return { data: savedRelicensePoints, source: "saved" };
  }
}

export async function fetchDescendants(
  id: string,
  k = 50,
): Promise<{ data: Descendants | null; source: Source | "down" | "none" }> {
  try {
    const data = await getJson<Descendants>(`/api/descendants/${idPath(id)}?k=${k}`, 20000, 600);
    return { data, source: "live" };
  } catch (err) {
    if (err instanceof NotFound) return { data: null, source: "none" };
    const saved = savedDescendants(id);
    return saved ? { data: saved, source: "saved" } : { data: null, source: "down" };
  }
}

export async function search(q: string, limit = 8, signal?: AbortSignal): Promise<SearchHit[]> {
  const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}&limit=${limit}`, { signal });
  if (!res.ok) throw new ApiDown(String(res.status));
  return (await res.json()) as SearchHit[];
}

export async function fetchSubstitutes(
  id: string,
  k = 5,
): Promise<{ data: Substitutes | null; source: Source | "down" | "none" }> {
  try {
    const data = await getJson<Substitutes>(`/api/substitutes/${idPath(id)}?k=${k}`, 20000);
    return { data, source: "live" };
  } catch (err) {
    if (err instanceof NotFound) return { data: null, source: "none" };
    const saved = savedSubstitutes(id);
    return saved ? { data: saved, source: "saved" } : { data: null, source: "down" };
  }
}

/** Runs the card-reading agent on a model's Hub card. The first call takes about 10 seconds. */
export async function readCard(id: string): Promise<{ data: ReadCardResult | null; source: Source | "down" }> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 90000);
  try {
    const res = await fetch(`${API_BASE}/api/read-card/${idPath(id)}`, { method: "POST", signal: ctrl.signal });
    if (!res.ok) throw new ApiDown(String(res.status));
    return { data: (await res.json()) as ReadCardResult, source: "live" };
  } catch {
    const saved = savedReadCard(id);
    return saved ? { data: saved, source: "saved" } : { data: null, source: "down" };
  } finally {
    clearTimeout(timer);
  }
}
