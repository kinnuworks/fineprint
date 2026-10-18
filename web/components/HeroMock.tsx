import { savedReport } from "@/lib/fallback";
import VerdictBadge, { DecisionBadge } from "./VerdictBadge";

const ID = "kenpath/svara-tts-v1";
const short = (id: string) => id.split("/").pop() ?? id;

/** Hero visual: a FinePrint report for a real model, drawn from its saved API response. */
export default function HeroMock() {
  const r = savedReport(ID, true);
  const oneHop = savedReport(ID, false);
  if (!r) return null;
  const lien = r.liens[0];
  const path = lien?.paths[0];
  const clauses = lien
    ? [
        ...lien.clauses.filter((c) => /1bi-[abc]$/.test(c.code)),
        ...lien.clauses.filter((c) => !/1bi-[abc]$/.test(c.code)),
      ].slice(0, 3)
    : [];

  return (
    <div className="stage" aria-hidden="true">
      <div className="window mock">
        <div className="window__bar">
          <span className="lights">
            <i />
            <i />
            <i />
          </span>
          <span className="window__title">FinePrint</span>
        </div>
        <div className="mock__body">
          <div className="mock__main">
            <span className="mock__label">Report</span>
            <p className="mock__id">{r.model}</p>
            <div className="mock__row">
              <DecisionBadge decision={r.decision} verdict={r.verdict} large />
              <VerdictBadge verdict={r.verdict} large />
            </div>
            <p style={{ marginTop: 10, fontWeight: 600 }}>{r.why}</p>
            {path && (
              <>
                <p className="mock__label" style={{ marginTop: 16 }}>
                  Chain of title
                </p>
                <div className="strip">
                  {path.models.map((m, i) => {
                    const lic = path.licenses?.[i];
                    const restricted = lic && lic === lien.license;
                    return (
                      <span key={m} style={{ display: "contents" }}>
                        <span className={`strip__node${restricted ? " strip__node--restricted" : ""}`}>{short(m)}</span>
                        {i < path.models.length - 1 && <span className="strip__arrow">&rarr;</span>}
                      </span>
                    );
                  })}
                </div>
              </>
            )}
            <div className="mock__facts">
              <div>
                <span className="mock__label">Declared</span>
                <b className="mono">{r.declared_license}</b>
              </div>
              <div>
                <span className="mock__label">Upstream</span>
                <b className="mono" style={{ color: "var(--lic-restricted)" }}>
                  {lien?.license}
                </b>
              </div>
              <div>
                <span className="mock__label">Ancestors</span>
                <b>{r.ancestors.length}</b>
              </div>
            </div>
          </div>
          <div className="mock__side">
            <span className="mock__label">
              {lien?.family} terms, {lien?.depth} hops up
            </span>
            <div className="clause-rows">
              {clauses.map((c) => (
                <div className="clause-row" key={c.code}>
                  <p>{c.obligation}</p>
                  <q>{c.quote}</q>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {lien && (
        <div className="float float--a">
          <div className="float__inner">
            <DecisionBadge decision={r.decision} verdict={r.verdict} />
            <span>
              for commercial use · {lien.family} terms, {lien.depth} hops up
            </span>
          </div>
        </div>
      )}
      {oneHop && (
        <div className="float float--b">
          <div className="float__inner">
            <VerdictBadge verdict={oneHop.verdict} />
            <span>Direct parents only: looks clean</span>
          </div>
        </div>
      )}
      <div className="float float--c">
        <div className="float__inner">
          <span className="t-mono">
            $ fineprint check . <span className="t-dim">&rarr;</span>{" "}
            {r.decision === "BLOCK" ? (
              <span className="fail">exit 1, build fails</span>
            ) : (
              <span className="note">exit 0, 1 model with conditions</span>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
