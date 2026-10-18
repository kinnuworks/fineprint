"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchReport } from "@/lib/api";
import { licClass, num } from "@/lib/format";
import { modelHref } from "@/lib/site";
import type { Report, Source } from "@/lib/types";
import SearchBox from "./SearchBox";
import VerdictBadge, { DecisionBadge } from "./VerdictBadge";

export interface Hero {
  id: string;
  label: string;
}

type Loaded = { id: string; data: Report | null; source: Source | "down" };

/** "Try it here": pick a model, see its live report summary in place. */
export default function TryIt({ heroes }: { heroes: Hero[] }) {
  const [selected, setSelected] = useState(heroes[0]?.id ?? "");
  const [res, setRes] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!selected) return;
    let live = true;
    fetchReport(selected, true).then((r) => live && setRes({ id: selected, ...r }));
    return () => {
      live = false;
    };
  }, [selected]);

  const loading = !res || res.id !== selected;
  const r = loading ? null : res.data;
  const liens = r?.liens ?? [];

  return (
    <div className="try">
      <div className="card">
        <div>
          <p className="t-title">Pick a model.</p>
          <p className="t-small" style={{ marginTop: 4 }}>
            These are real models on the Hub. Each one loads a live report.
          </p>
        </div>
        <div className="chips" role="group" aria-label="Example models">
          {heroes.map((h) => (
            <button
              key={h.id}
              type="button"
              className="chip"
              aria-pressed={selected === h.id}
              onClick={() => setSelected(h.id)}
            >
              {h.label}
            </button>
          ))}
        </div>
        <div>
          <p className="t-small" style={{ marginBottom: 8 }}>
            Or search any public model.
          </p>
          <SearchBox placeholder="Model id or Hugging Face URL" onPick={(id) => setSelected(id)} />
        </div>
      </div>

      <div className="stage stage--soft try__stage">
        <div className="window">
          <div className="window__bar">
            <span className="lights" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span className="window__title">FinePrint</span>
          </div>
          <div className="preview" aria-live="polite" aria-busy={loading}>
            <div className="preview__head">
              <div style={{ minWidth: 0 }}>
                <span className="mock__label">Report</span>
                <p className="mock__id break">{selected}</p>
              </div>
              {r && (
                <div className="mock__row" style={{ marginTop: 0 }}>
                  <DecisionBadge decision={r.decision} verdict={r.verdict} />
                  <VerdictBadge verdict={r.verdict} />
                </div>
              )}
            </div>
            {loading && (
              <>
                <div className="skeleton" style={{ width: "70%" }} />
                <div className="skeleton" style={{ width: "90%" }} />
                <div className="skeleton" style={{ width: "50%" }} />
              </>
            )}
            {!loading && !r && (
              <p className="preview__why">The FinePrint API is not reachable right now. Try one of the chips.</p>
            )}
            {r && (
              <>
                <p className="preview__why">{r.why ?? r.reason}</p>
                <div className="preview__grid">
                  <div>
                    <span className="mock__label">Declared</span>
                    <b>
                      <span className={licClass(r.declared_license)}>{r.declared_license ?? "none"}</span>
                    </b>
                  </div>
                  <div>
                    <span className="mock__label">Upstream terms</span>
                    <b>
                      {liens.length ? (
                        [...new Set(liens.map((l) => l.license))].map((l) => (
                          <span key={l} className={licClass(l)} style={{ marginRight: 4 }}>
                            {l}
                          </span>
                        ))
                      ) : (
                        <span className="t-small">none found</span>
                      )}
                    </b>
                  </div>
                  <div>
                    <span className="mock__label">Ancestors read</span>
                    <b>{num(r.ancestors.length)}</b>
                  </div>
                </div>
                {liens.length > 0 && (
                  <ul className="preview__liens">
                    {liens.slice(0, 2).map((l) => (
                      <li key={l.family}>
                        <b>{l.family}</b>
                        <span className="t-small"> via {l.via}</span>
                        {l.clauses[0] && <p style={{ marginTop: 4 }}>{l.clauses[0].obligation}</p>}
                      </li>
                    ))}
                  </ul>
                )}
                {res?.source === "saved" && (
                  <p className="t-small" style={{ marginTop: 10 }}>
                    Saved copy: the API is not reachable.
                  </p>
                )}
                <div style={{ marginTop: 16 }}>
                  <Link className="btn btn-ink btn-sm" href={modelHref(selected)}>
                    Open the full report
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
