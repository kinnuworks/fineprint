"use client";

import Link from "next/link";
import { useState } from "react";
import { runWhatIf, type WhatIfError } from "@/lib/api";
import { compact, licClass, num } from "@/lib/format";
import { modelHref } from "@/lib/site";
import type { WhatIf } from "@/lib/types";
import { secs } from "@/lib/whatif";

const ERRORS: Record<WhatIfError, string> = {
  not_found: "This model is not in the graph, so there is no family to copy.",
  not_possible: "A relicensing simulation cannot run for this model.",
  busy: "Another simulation is running. Try again in a minute.",
  down: "The simulation could not run right now. Try again in a moment.",
  unsupported: "The API answering here can only simulate the FLUX.1-dev family, so this model cannot be run yet.",
};

/** "What if <root> were relicensed?" Runs on a throwaway GRAPH.COPY; the shared graph is not changed. */
export default function WhatIfAction({ root, license = "apache-2.0" }: { root: string; license?: string }) {
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<WhatIf | null>(null);
  const [error, setError] = useState<{ kind: WhatIfError; detail?: string } | null>(null);

  const run = async () => {
    setPhase("running");
    setError(null);
    const res = await runWhatIf(root, license);
    if (res.data) {
      setResult(res.data);
      setPhase("done");
    } else {
      setError({ kind: res.error, detail: res.detail });
      setPhase("error");
    }
  };

  if (phase === "idle" || (phase === "error" && !result)) {
    return (
      <div className="whatif">
        <button className="btn btn-outline btn-sm" type="button" onClick={run}>
          What if {root} were relicensed?
        </button>
        {phase === "error" && error && (
          <p className="small muted" role="status" style={{ marginTop: 6 }}>
            {error.kind === "not_possible" && error.detail ? error.detail : ERRORS[error.kind]}
          </p>
        )}
      </div>
    );
  }

  if (phase === "running") {
    return (
      <div className="whatif">
        <div className="progress" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <span>Copying the family of {root} with GRAPH.COPY and walking it as {license}</span>
        </div>
      </div>
    );
  }

  const r = result!;
  const s = r.seconds;
  const timing = [
    secs(s.graph_copy) && `GRAPH.COPY in ${secs(s.graph_copy)}`,
    secs(s.walks) && `walks in ${secs(s.walks)}`,
    s.delete != null && "copy deleted",
  ].filter(Boolean);

  return (
    <div className="whatif whatif--done" aria-live="polite">
      <div className="whatif__head">
        <span className="tier">Simulation</span>
        <p className="small" style={{ fontWeight: 600 }}>
          If <span className="mono break">{r.root ?? root}</span> were relicensed
          {r.from_license ? (
            <>
              {" "}
              from <span className={licClass(r.from_license)}>{r.from_license}</span>
            </>
          ) : null}{" "}
          to <span className={licClass(r.to_license ?? license)}>{r.to_license ?? license}</span>
        </p>
      </div>
      <dl className="facts whatif__facts">
        <div>
          <dt>Family</dt>
          <dd>
            {num(r.family_models)} model{r.family_models === 1 ? "" : "s"}
          </dd>
        </div>
        <div>
          <dt>Affected, before &rarr; after</dt>
          <dd>
            {num(r.before.affected_total)} &rarr; {num(r.after.affected_total)}
          </dd>
        </div>
        <div>
          <dt>Still labelled restricted</dt>
          <dd>{num(r.still_restricted_after)}</dd>
        </div>
      </dl>
      {r.why && <p className="small">{r.why}</p>}
      {r.relabel_needed.length > 0 && (
        <div>
          <p className="small muted">Most downloaded models that would need a new label:</p>
          <ul className="whatif__list">
            {r.relabel_needed.slice(0, 3).map((m) => (
              <li key={m.id}>
                <Link className="mono break" href={modelHref(m.id)}>
                  {m.id}
                </Link>{" "}
                <span className={licClass(m.license)}>{m.license ?? "none"}</span>
                {m.downloads != null && <span className="small muted"> {compact(m.downloads)} downloads</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="small muted">
        Run on a throwaway copy
        {r.copy_graph ? (
          <>
            {" "}
            (<span className="mono">{r.copy_graph}</span>)
          </>
        ) : null}{" "}
        of the family graph. The shared graph is not changed.
        {timing.length ? ` ${timing.join(", ")}.` : ""}
        {r.cached_family ? " Family graph reused from an earlier run." : ""}
      </p>
    </div>
  );
}
