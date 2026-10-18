export type Verdict = "NO LIENS FOUND" | "LIENS" | "CLOUDED" | "UNKNOWN";

export interface Ancestor {
  id: string;
  license: string | null;
  depth: number;
  /** The model this ancestor was reached from: the edge is child -[relation]-> id. */
  child?: string;
  relation?: string;
  /** True when the ancestor is no longer on the Hub. */
  missing?: boolean;
}

export interface Clause {
  code: string;
  obligation: string;
  quote: string;
  source: string;
  tier: string;
}

export interface ProofPath {
  models: string[];
  licenses?: (string | null)[];
  relations?: string[];
  /** "card" when the edge was read from the model card rather than Hub tags. */
  source?: string;
  quote?: string;
}

export interface Lien {
  family: string;
  license: string;
  tier: string;
  via: string;
  depth: number;
  clauses: Clause[];
  paths: ProofPath[];
}

export type Decision = "ALLOW" | "CONDITIONS" | "BLOCK";
export type Use = "commercial" | "noncommercial";

export interface DatasetLink {
  model: string;
  dataset: string;
  license: string | null;
  missing?: boolean;
  source?: string;
  quote?: string | null;
}

export type DeletedAncestor = string | { id: string; [k: string]: unknown };

export interface Ruling {
  id: string;
  scope: "license" | "model";
  target: string;
  effect: "approve" | "reject";
  use: "commercial" | "non-commercial" | "any";
  conditions?: string;
  note: string;
  by?: string;
  at?: string;
  /** Why this ruling did or did not change the decision. */
  why?: string;
}

/** What an org's recorded rulings changed in this report. */
export interface OrgRulings {
  org: string;
  applied: Ruling[];
  not_applied: Ruling[];
  decision_before: Decision | "N/A";
  decision_after: Decision | "N/A";
}

export interface Report {
  model: string;
  declared_license?: string | null;
  downloads_30d?: number | null;
  verdict: Verdict;
  reason: string;
  detail?: string;
  coverage: number | null;
  ancestors: Ancestor[];
  liens: Lien[];
  graph?: boolean;
  disclaimer: string;
  decision?: Decision;
  why?: string;
  use?: Use;
  /** "full lineage" or "direct parents only" */
  mode?: string;
  /** "graph" or "live Hub lookup" */
  source?: string;
  deleted_ancestors?: DeletedAncestor[];
  datasets?: DatasetLink[];
  /** For a model deleted from the Hub: how many models still declare it as an ancestor. */
  descendants?: number;
  /** For a model deleted from the Hub: how many declare it as their direct base. */
  direct_children?: number;
  unresolved_card_claims?: number;
  /** Present when a ruleset was asked for. */
  org?: OrgRulings;
}

export interface Descendant {
  id: string;
  license: string | null;
  downloads: number | null;
  depth: number;
}

export interface Descendants {
  model: string;
  stats: { count: number; deepest: number; downloads: number };
  top: Descendant[];
}

export interface SearchHit {
  id: string;
  license: string | null;
  downloads: number | null;
}

export interface TopMismatch {
  id: string;
  declared: string;
  inherits: string[];
  relation: string;
  downloads_30d: number;
}

export interface GraphAudit {
  computed_in?: string;
  at?: string;
  numbers: Record<string, unknown> & {
    models_total?: number[];
    inheriting_restricted?: number[];
    inheriting_but_declare_permissive?: number[];
    of_those_ship_license_file?: number[];
    non_commercial_upstream_declare_permissive?: number[];
    by_family?: [string, number][];
  };
  seconds?: Record<string, number>;
}

export interface HubApiComparison {
  root: string;
  descendants: number;
  hub_api_calls_needed: number;
  median_call_seconds: number;
  estimated_sequential_minutes: number;
  graph_descendants?: number;
  graph_ms_median?: number;
}

export interface LoadBearing {
  seconds?: number;
  query?: string;
  note?: string;
  top: {
    id: string;
    license: string | null;
    downloads_30d: number | null;
    score: number;
    descendants?: number;
    descendant_downloads_30d?: number;
  }[];
}

export interface RelicensePoints {
  computed_in?: string;
  relicensing_points: number;
  points_with_mismatched_descendants?: number;
  mismatched_models_below_some_point?: number;
  // Field names from an earlier API version.
  points_that_spread_to_others?: number;
  mismatches_inherited_from_someone_else?: number;
  top: {
    model: string;
    declared?: string | null;
    restricted_parents?: string[];
    restricted_parent?: string[];
    mismatched_models_below: number;
    their_downloads_30d: number | null;
    own_downloads_30d: number | null;
  }[];
}

export interface WhatIf {
  scenario: string;
  family_models: number;
  before: { models_under_nc_license: number; models_below_one: number; affected_total: number };
  after: { models_under_nc_license: number; models_below_one: number; affected_total: number };
  still_non_commercial_after: number;
  why?: string;
}

export interface UnslothNumbers {
  mismatched: number;
  via_unsloth: number;
  share: number;
  template_signature: number;
  template_share: number;
  template_signature_rule: string;
}

export interface Stats {
  computed_in?: string;
  models_total?: number;
  inheriting_restricted?: number;
  inheriting_but_declare_permissive?: number;
  their_downloads_30d?: number;
  ship_license_file?: number;
  non_commercial_upstream_declare_permissive?: number;
  non_commercial_downloads_30d?: number;
  contested_only?: number;
  by_family?: [string, number][];
  graph_audit?: GraphAudit;
  hub_api_comparison?: HubApiComparison;
  unsloth?: UnslothNumbers;
  duckdb_cross_check?: { note?: string; max_inheritance_depth?: number; [k: string]: unknown };
  // Earlier dump-based fields, still read when present.
  models_inheriting_restrictive_terms?: number;
  of_those_declaring_permissive_license?: number;
  max_inheritance_depth?: number;
  mismatch_by_family?: Record<string, number>;
  top_by_downloads?: TopMismatch[];
}

/** Where a payload came from: the live API or a saved copy shipped with the site. */
export type Source = "live" | "saved";

export interface CardClaim {
  kind: string;
  name: string;
  quote: string;
  status: string;
  target: string | null;
  about?: string;
}

export interface ReadCardResult {
  model: string;
  before: Verdict;
  after: Verdict;
  edges_written: number;
  claims: CardClaim[];
  report: Report;
  cached: boolean;
  /** "recorded" when the live model call failed and a saved read of the card was replayed. */
  source?: "live" | "cache" | "recorded";
  recorded_at?: string | null;
  /** False when the server removed the card edges again after answering. */
  kept?: boolean;
}

export interface Substitute {
  id: string;
  license: string | null;
  params: number | null;
  downloads_30d: number | null;
}

export interface Substitutes {
  model: string;
  task?: string | null;
  params?: number | null;
  substitutes: Substitute[];
  note?: string;
}
