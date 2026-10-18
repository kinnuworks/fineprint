"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DEMO_RULESET, fetchReport } from "@/lib/api";
import { savedIds } from "@/lib/fallback";
import {
  VERDICT_HELP,
  decisionView,
  hopRelations,
  licClass,
  num,
  pct,
  relationLabel,
  relationPhrase,
  verdictKey,
} from "@/lib/format";
import { modelHref } from "@/lib/site";
import type { DeletedAncestor, Lien, OrgRulings, Report, Ruling, Source, Use } from "@/lib/types";
import Alternatives from "./Alternatives";
import Downstream from "./Downstream";
import LineageGraph from "./LineageGraph";
import ReadCard from "./ReadCard";
import SafeBoundary from "./SafeBoundary";
import SearchBox from "./SearchBox";
import VerdictBadge, { DecisionBadge } from "./VerdictBadge";

type Loaded = { data: Report | null; source: Source | "down" };

function plainQuote(s: string): string {
  return s.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").trim();
}

function sentence(s: string) {
  const t = s.trim();
  if (!t) return t;
  const cap = t[0].toUpperCase() + t.slice(1);
  return /[.!?]$/.test(cap) ? cap : cap + ".";
}

const hubUrl = (id: string) => `https://huggingface.co/${id}`;

function Lic({ license }: { license: string | null | undefined }) {
  return <span className={licClass(license)}>{license ?? "none declared"}</span>;
}

function LienBlock({ lien }: { lien: Lien }) {
  const viaIsDataset = lien.paths.some((p) => {
    const rels = hopRelations(p);
    return p.models[p.models.length - 1] === lien.via && rels[rels.length - 1] === "TRAINED_ON";
  });
  return (
    <article className="lien">
      <div className="lien-head">
        <h3>{lien.family}</h3>
        <Lic license={lien.license} />
        <span className={`tier tier--${lien.tier}`}>{lien.tier}</span>
      </div>
      <p className="small muted break" style={{ marginTop: 4 }}>
        {lien.depth === 0 ? (
          "Comes from this model's own declared license."
        ) : (
          <>
            Arrives through{" "}
            {viaIsDataset ? (
              <a className="link" href={`https://huggingface.co/datasets/${lien.via}`} target="_blank" rel="noreferrer">
                dataset {lien.via}
              </a>
            ) : (
              <Link className="link" href={modelHref(lien.via)}>
                {lien.via}
              </Link>
            )}
            , {lien.depth} level{lien.depth === 1 ? "" : "s"} up.
          </>
        )}
      </p>
      <ul className="clauses">
        {lien.clauses.map((c) => (
          <li key={c.code}>
            <p className="clause-ob">{c.obligation}</p>
            <blockquote className="clause-quote">&ldquo;{c.quote}&rdquo;</blockquote>
            <div className="clause-meta">
              <span className="mono">{c.code}</span>
              <span>{c.tier}</span>
              <a href={c.source} target="_blank" rel="noreferrer">
                Source text
              </a>
            </div>
          </li>
        ))}
      </ul>
      {lien.paths.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="small" style={{ fontWeight: 600 }}>
            {lien.paths.length === 1 ? "Proof path" : `${lien.paths.length} proof paths`}
          </p>
          {lien.paths.map((p, i) => {
            const rels = hopRelations(p);
            return (
              <div key={i}>
                <ol className="path" aria-label={`Proof path ${i + 1}`}>
                  {p.models.map((m, j) => {
                    const lic = p.licenses?.[j] ?? (m === lien.via ? lien.license : null);
                    const isDataset = j > 0 && rels[j - 1] === "TRAINED_ON";
                    const inner = (
                      <>
                        {m} <span className={licClass(lic)}>{lic ?? "none"}</span>
                      </>
                    );
                    return (
                      <li key={m + j} style={{ display: "contents" }}>
                        {isDataset ? (
                          <a
                            className="hop"
                            href={`https://huggingface.co/datasets/${m}`}
                            target="_blank"
                            rel="noreferrer"
                            title={`Dataset ${m}`}
                          >
                            {inner}
                          </a>
                        ) : (
                          <Link className="hop" href={modelHref(m)} title={`${m} (${lic ?? "no license"})`}>
                            {inner}
                          </Link>
                        )}
                        {j < rels.length && <span className="rel">{relationPhrase(rels[j])}</span>}
                      </li>
                    );
                  })}
                </ol>
                {p.source === "card" && (
                  <p className="small muted" style={{ marginTop: 4 }}>
                    Stated in the model card{p.quote ? <>: &ldquo;{plainQuote(p.quote)}&rdquo;</> : "."}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

const modeKey = (graph: boolean, use: Use, rs = "") => `${graph ? "full" : "one"}|${use}|${rs}`;

const RULING_USE: Record<string, string> = { commercial: "commercial", "non-commercial": "non-commercial", any: "any use" };

function RulingItem({ r }: { r: Ruling }) {
  return (
    <li>
      <div className="lien-head">
        <span className={`tier ruling--${r.effect}`}>{r.effect}</span>
        <span className="mono break">{r.target}</span>
        <span className="small muted">
          {r.scope} · {RULING_USE[r.use] ?? r.use}
        </span>
      </div>
      <p className="clause-ob" style={{ marginTop: 6 }}>
        {r.note}
      </p>
      {r.conditions && <p className="small">Conditions: {sentence(r.conditions)}</p>}
      <div className="clause-meta">
        <span className="mono">{r.id}</span>
        {r.by && <span>{r.by}</span>}
        {r.at && <span>{r.at.slice(0, 10)}</span>}
        {r.why && <span>{r.why}</span>}
      </div>
    </li>
  );
}

function OrgPanel({ org, verdict }: { org: OrgRulings; verdict: string }) {
  if (!org.applied.length && !org.not_applied.length) {
    return (
      <p className="notice" role="status">
        No ruling in <span className="mono">{org.org}</span> matches this model, so its decision is unchanged.
      </p>
    );
  }
  return (
    <section className="card" aria-labelledby="org-h">
      <div className="card-head">
        <h2 id="org-h">{org.applied.length ? "Org rulings applied" : "Org rulings matched, not applied"}</h2>
        <p>
          From <span className="mono">{org.org}</span>, a separate graph (org:{org.org}) only this org reads.
        </p>
      </div>
      <div className="org-flip" aria-label="Decision before and after org rulings">
        <span className="small muted">Decision</span>
        <DecisionBadge decision={org.decision_before} verdict={verdict} />
        <span aria-hidden="true">→</span>
        <span className="sr-only">becomes</span>
        <DecisionBadge decision={org.decision_after} verdict={verdict} />
      </div>
      <ul className="clauses">
        {org.applied.map((r) => (
          <RulingItem key={r.id} r={r} />
        ))}
      </ul>
      {org.not_applied.length > 0 && (
        <>
          <p className="small" style={{ fontWeight: 600, marginTop: 12 }}>
            Matched but not applied (FinePrint fails closed)
          </p>
          <ul className="clauses">
            {org.not_applied.map((r) => (
              <RulingItem key={r.id} r={r} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
const USE_LABEL: Record<Use, string> = { commercial: "commercial use", noncommercial: "non-commercial use" };

function deletedId(d: DeletedAncestor): string {
  return typeof d === "string" ? d : d.id;
}

export default function ReportView({
  id,
  initial,
  initialGraph,
  initialUse,
  initialRuleset = "",
  hasOrg,
}: {
  id: string;
  initial: Loaded;
  initialGraph: boolean;
  initialUse: Use;
  initialRuleset?: string;
  hasOrg: boolean;
}) {
  const [graphOn, setGraphOn] = useState(initialGraph);
  const [use, setUse] = useState<Use>(initialUse);
  const [ruleset, setRuleset] = useState(initialRuleset);
  const [cache, setCache] = useState<Record<string, Loaded>>({
    [modeKey(initialGraph, initialUse, initialRuleset)]: initial,
  });
  const rulesets = [...new Set(["", DEMO_RULESET, initialRuleset])];

  const load = (graph: boolean, u: Use, rs: string) => {
    const key = modeKey(graph, u, rs);
    fetchReport(id, graph, u, rs).then((res) => setCache((c) => (c[key] ? c : { ...c, [key]: res })));
  };

  // Fetch the other lineage mode in the background so the side-by-side is ready.
  const otherKey = modeKey(!graphOn, use, ruleset);
  const haveOther = Boolean(cache[otherKey]);
  useEffect(() => {
    if (!haveOther) load(!graphOn, use, ruleset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haveOther, graphOn, use, ruleset]);

  const current = cache[modeKey(graphOn, use, ruleset)];
  // While another view loads, keep showing one already on screen.
  const pending = !current;
  const shown = current ?? cache[modeKey(!graphOn, use, ruleset)] ?? Object.values(cache)[0];

  const setUrl = (graph: boolean, u: Use, rs: string) => {
    const url = new URL(window.location.href);
    if (graph) url.searchParams.delete("graph");
    else url.searchParams.set("graph", "false");
    if (u === "commercial") url.searchParams.delete("use");
    else url.searchParams.set("use", u);
    if (rs) url.searchParams.set("ruleset", rs);
    else url.searchParams.delete("ruleset");
    window.history.replaceState(null, "", url.toString());
  };

  const switchGraph = (on: boolean) => {
    setGraphOn(on);
    setUrl(on, use, ruleset);
    if (!cache[modeKey(on, use, ruleset)]) load(on, use, ruleset);
  };

  const switchUse = (u: Use) => {
    setUse(u);
    setUrl(graphOn, u, ruleset);
    if (!cache[modeKey(graphOn, u, ruleset)]) load(graphOn, u, ruleset);
  };

  const switchRuleset = (rs: string) => {
    setRuleset(rs);
    setUrl(graphOn, use, rs);
    if (!cache[modeKey(graphOn, use, rs)]) load(graphOn, use, rs);
  };

  const [cardNote, setCardNote] = useState(false);

  const onCardReport = (r: Report, kept: boolean | undefined) => {
    // The card read changes the lineage, so every cached view is stale.
    // The card read answers without org rulings, so the view goes back to none.
    setCardNote(kept === false);
    const key = modeKey(true, (r.use as Use) ?? "commercial");
    setCache({ [key]: { data: r, source: "live" } });
    if (!graphOn) setGraphOn(true);
    if (ruleset) {
      setRuleset("");
      setUrl(true, use, "");
    }
    if (key !== modeKey(true, use)) load(true, use, "");
  };

  const report = shown?.data ?? null;
  const source = shown?.source;

  const top = (
    <div className="report-top">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">FinePrint</Link>
        <span aria-hidden="true">/</span>
        <span className="mono break">{id}</span>
      </nav>
      <div style={{ flex: "1 1 320px", maxWidth: 460 }}>
        <SearchBox placeholder="Check another model" showKbd />
      </div>
    </div>
  );

  if (!shown) {
    return <ReportSkeleton id={id} />;
  }

  if (!report) {
    return (
      <div className="app-stack">
        {top}
        <section className="card">
          <h1>{id}</h1>
          <h2 style={{ marginTop: 12 }}>The FinePrint API is not reachable.</h2>
          <p className="muted" style={{ marginTop: 6 }}>
            This report cannot be fetched right now. Saved reports are available for these models:
          </p>
          <div className="chips" style={{ marginTop: 12 }}>
            {savedIds.map((s) => (
              <Link key={s} className="chip mono" href={modelHref(s)}>
                {s}
              </Link>
            ))}
          </div>
        </section>
      </div>
    );
  }

  const vk = verdictKey(report.verdict);
  const inherited = [...new Set(report.liens.map((l) => l.license))];
  // UNKNOWN with full lineage means FinePrint has no lineage to read for this id.
  const isUnknown = report.verdict === "UNKNOWN" && graphOn;
  const full = cache[modeKey(true, use, ruleset)]?.data;
  const oneHop = cache[modeKey(false, use, ruleset)]?.data;
  const deleted = report.deleted_ancestors ?? [];
  const datasets = report.datasets ?? [];
  const reportUse: Use = (report.use as Use) ?? use;
  const dv = decisionView(report.decision, report.verdict);

  return (
    <div className="app-stack">
      {top}

      {cardNote && (
        <div className="notice" role="status">
          This report includes lineage read from the model card. Shown from this read; the shared graph is left as the
          Hub tags have it.
        </div>
      )}

      {source === "saved" && (
        <div className="notice notice--warn" role="status">
          The FinePrint API is not reachable, so this is a saved copy of the report from Oct 18 2026.
        </div>
      )}

      <section className="card">
        <p className="small muted">Report</p>
        <h1 style={{ marginTop: 2 }}>{report.model}</h1>
        <p className="small" style={{ marginTop: 6 }}>
          <a className="link" href={hubUrl(report.model)} target="_blank" rel="noreferrer">
            View on Hugging Face
          </a>
          {report.source === "live Hub lookup" && (
            <span className="muted"> · read from a live Hub lookup, not the graph snapshot</span>
          )}
        </p>

        <div className="panels">
          {dv && (
            <div className={`panel-v panel-v--${dv.key}`}>
              <span className="label">Decision for {USE_LABEL[reportUse]}</span>
              <span>
                <DecisionBadge decision={report.decision} verdict={report.verdict} large />
              </span>
              {report.why && <p className="why">{sentence(report.why)}</p>}
            </div>
          )}
          <div className={`panel-v panel-v--${vk}`}>
            <span className="label">Title verdict</span>
            <span>
              <VerdictBadge verdict={report.verdict} large />
            </span>
            <p className="why">{sentence(report.reason)}</p>
          </div>
        </div>
        {report.detail && !isUnknown && (
          <p className="muted" style={{ marginTop: 10 }}>
            {report.detail}
          </p>
        )}
        {VERDICT_HELP[vk] && (
          <p className="small muted" style={{ marginTop: 10 }}>
            {VERDICT_HELP[vk]}
          </p>
        )}

        <div className="controls">
          <div className="segmented" role="group" aria-label="Intended use">
            <button type="button" aria-pressed={use === "commercial"} onClick={() => switchUse("commercial")}>
              Commercial
            </button>
            <button type="button" aria-pressed={use === "noncommercial"} onClick={() => switchUse("noncommercial")}>
              Non-commercial
            </button>
          </div>
          {!isUnknown && (
            <div className="segmented" role="group" aria-label="Lineage depth">
              <button type="button" aria-pressed={graphOn} onClick={() => switchGraph(true)}>
                Full lineage
              </button>
              <button type="button" aria-pressed={!graphOn} onClick={() => switchGraph(false)}>
                Direct parents only (what the model page shows)
              </button>
            </div>
          )}
          <div className="segmented" role="group" aria-label="Org rulings">
            {rulesets.map((rs) => (
              <button key={rs || "none"} type="button" aria-pressed={ruleset === rs} onClick={() => switchRuleset(rs)}>
                {rs ? `Org rulings: ${rs}` : "No org rulings"}
              </button>
            ))}
          </div>
          {pending && (
            <span className="progress">
              <span className="spinner" aria-hidden="true" /> Loading
            </span>
          )}
        </div>

        {!isUnknown && full && oneHop && (
          <div className="side-by-side" aria-label="Full lineage compared with direct parents only">
            {(
              [
                ["Full lineage", full],
                ["Direct parents only", oneHop],
              ] as [string, Report][]
            ).map(([label, r]) => (
              <div key={label}>
                <span className="small muted">{label}</span>
                <div className="badges">
                  <VerdictBadge verdict={r.verdict} />
                  <DecisionBadge decision={r.decision} verdict={r.verdict} />
                </div>
                <span className="small muted">
                  {r.ancestors.length} ancestor{r.ancestors.length === 1 ? "" : "s"} read
                </span>
              </div>
            ))}
          </div>
        )}

        <dl className="facts">
          <div>
            <dt>Declared license</dt>
            <dd>
              <Lic license={report.declared_license} />
            </dd>
          </div>
          <div>
            <dt>Upstream terms</dt>
            <dd>
              {inherited.length ? (
                inherited.map((l) => (
                  <span key={l} style={{ marginRight: 6 }}>
                    <Lic license={l} />
                  </span>
                ))
              ) : (
                <span className="muted">{isUnknown ? "unknown" : "none found"}</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Chain coverage</dt>
            <dd title="Share of the upstream chain whose license is known">
              {report.coverage == null ? <span className="muted">n/a one hop up</span> : pct(report.coverage, 0)}
            </dd>
          </div>
          <div>
            <dt>Ancestors read</dt>
            <dd>{num(report.ancestors.length)}</dd>
          </div>
          {report.downloads_30d != null && (
            <div>
              <dt>Downloads, 30 days</dt>
              <dd>{num(report.downloads_30d)}</dd>
            </div>
          )}
        </dl>
      </section>

      {ruleset && report.org && <OrgPanel org={report.org} verdict={report.verdict} />}
      {ruleset && !report.org && (
        <p className="notice notice--warn" role="status">
          Org rulings from <span className="mono">{ruleset}</span> are not in this copy of the report, so its decision
          ignores them.
        </p>
      )}

      {deleted.length > 0 && (
        <div className="notice notice--warn" role="note">
          {deleted.length} ancestor{deleted.length === 1 ? " has" : "s have"} been deleted from the Hub, so their terms
          cannot be read:{" "}
          {deleted.map((d, i) => (
            <span key={deletedId(d)}>
              {i > 0 && ", "}
              <code className="mono break">{deletedId(d)}</code>
            </span>
          ))}
          .
        </div>
      )}

      {isUnknown ? (
        <section className="card">
          <h2>No finding possible.</h2>
          {report.detail && <p style={{ marginTop: 6 }}>{report.detail}</p>}
          {(report.direct_children != null || report.descendants != null) && (
            <dl className="facts">
              {report.direct_children != null && (
                <div>
                  <dt>Direct children</dt>
                  <dd>{num(report.direct_children)}</dd>
                </div>
              )}
              {report.descendants != null && (
                <div>
                  <dt>All descendants</dt>
                  <dd>{num(report.descendants)}</dd>
                </div>
              )}
            </dl>
          )}
          <p className="small muted" style={{ marginTop: 8 }}>
            UNKNOWN means FinePrint could not reach a finding, so treat the model as unchecked. Check the id on{" "}
            <a className="link" href={hubUrl(report.model)} target="_blank" rel="noreferrer">
              Hugging Face
            </a>{" "}
            or search again above.
          </p>
        </section>
      ) : (
        <section className="card" aria-labelledby="chain-h">
          <div className="card-head">
            <h2 id="chain-h">Chain of title</h2>
            <span className="chip chip--soft">{report.mode ?? (graphOn ? "full lineage" : "direct parents only")}</span>
          </div>
          {report.graph === false && (
            <p className="small muted" style={{ marginBottom: 10 }}>
              Direct parents only: one hop up, as the model page on Hugging Face shows. Switch to full lineage to read
              every ancestor.
            </p>
          )}
          <SafeBoundary
            key={report.model + String(report.graph) + report.liens.length + report.ancestors.length}
            fallback={
              <p className="notice">The graph view could not be drawn. The proof paths below list the same chain.</p>
            }
          >
            <LineageGraph report={report} />
          </SafeBoundary>
        </section>
      )}

      {hasOrg && graphOn && (!isUnknown || report.downloads_30d != null) && (
        <ReadCard id={id} onReport={onCardReport} />
      )}

      {report.liens.length > 0 && (
        <section className="card" aria-labelledby="liens-h">
          <div className="card-head">
            <h2 id="liens-h">
              {report.liens.length} lien{report.liens.length === 1 ? "" : "s"}
            </h2>
            <p>Obligations from upstream licenses, with the clause each rests on and every path it takes.</p>
          </div>
          {report.liens.map((l, i) => (
            <LienBlock key={l.family + i} lien={l} />
          ))}
        </section>
      )}

      {hasOrg && graphOn && (report.verdict === "CLOUDED" || report.verdict === "LIENS") && (
        <Alternatives id={report.model} />
      )}

      {!isUnknown && report.ancestors.length > 0 && (
        <section className="card" aria-labelledby="anc-h">
          <div className="card-head">
            <h2 id="anc-h">Ancestors</h2>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>License</th>
                  <th>Reached from</th>
                  <th className="num">Level</th>
                </tr>
              </thead>
              <tbody>
                {report.ancestors.map((a) => (
                  <tr key={a.id}>
                    <td className="idcell">
                      <Link href={modelHref(a.id)}>{a.id}</Link>
                      {a.missing && <span className="muted"> (deleted from the Hub)</span>}
                    </td>
                    <td>
                      <Lic license={a.license} />
                    </td>
                    <td className="idcell">
                      {a.child && a.relation ? (
                        <>
                          <Link href={modelHref(a.child)}>{a.child}</Link>
                          <span className="muted"> ({relationLabel(a.relation)})</span>
                        </>
                      ) : (
                        <span className="muted">n/a</span>
                      )}
                    </td>
                    <td className="num">{a.depth}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {datasets.length > 0 && (
        <section className="card" aria-labelledby="ds-h">
          <div className="card-head">
            <h2 id="ds-h">Training datasets</h2>
          </div>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>License</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((d) => (
                  <tr key={d.model + d.dataset}>
                    <td className="idcell">
                      {d.missing ? (
                        <>
                          {d.dataset} <span className="muted">(not found on the Hub)</span>
                        </>
                      ) : (
                        <a href={`https://huggingface.co/datasets/${d.dataset}`} target="_blank" rel="noreferrer">
                          {d.dataset}
                        </a>
                      )}
                    </td>
                    <td>
                      <Lic license={d.license || null} />
                    </td>
                    <td>
                      {d.source ?? "n/a"}
                      {d.model !== report.model && <span className="muted"> via {d.model}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {hasOrg && (!isUnknown || (report.descendants ?? 0) > 0) && <Downstream id={report.model} />}

      <p className="small muted">{report.disclaimer}</p>
    </div>
  );
}

export function ReportSkeleton({ id }: { id?: string }) {
  return (
    <div className="app-stack" aria-busy="true">
      <section className="card">
        <p className="small muted">Reading the fine print for</p>
        {id ? (
          <h1 style={{ marginTop: 2 }}>{id}</h1>
        ) : (
          <div className="skeleton" style={{ height: 26, width: "60%" }} />
        )}
        <div className="panels">
          <div className="skeleton" style={{ height: 110 }} />
          <div className="skeleton" style={{ height: 110 }} />
        </div>
      </section>
      <section className="card">
        <div className="skeleton" style={{ height: 300 }} />
      </section>
    </div>
  );
}
