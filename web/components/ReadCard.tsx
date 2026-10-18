"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { readCard } from "@/lib/api";
import { num } from "@/lib/format";
import type { ReadCardResult, Report, Source } from "@/lib/types";
import VerdictBadge from "./VerdictBadge";

/** Card text quotes carry markdown links; show the link text only. */
function plain(s: string): string {
  return s
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`]+/g, "")
    .replace(/\p{Extended_Pictographic}/gu, "")
    .replace(/^\s*\|+|\|+\s*$/g, "")
    .replace(/\s*\|\s*/g, " | ")
    .replace(/\s+/g, " ")
    .trim();
}

const KIND: Record<string, string> = {
  base_model: "Base model",
  finetuned_from: "Base model",
  dataset: "Dataset",
  generated_by: "Trained on outputs of",
};

function claimHref(kind: string, target: string): { href: string; internal: boolean } {
  if (kind === "dataset") return { href: `https://huggingface.co/datasets/${target}`, internal: false };
  return { href: "/" + target.split("/").map(encodeURIComponent).join("/"), internal: true };
}

export default function ReadCard({
  id,
  onReport,
}: {
  id: string;
  onReport: (r: Report, kept: boolean | undefined) => void;
}) {
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState<{ data: ReadCardResult; source: Source } | null>(null);

  useEffect(() => {
    if (phase !== "running") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  const run = async () => {
    setPhase("running");
    setSeconds(0);
    const res = await readCard(id);
    if (!res.data) {
      setPhase("error");
      return;
    }
    setResult({ data: res.data, source: res.source as Source });
    setPhase("done");
    if (res.data.report) onReport(res.data.report, res.data.kept);
  };

  const step =
    seconds < 3
      ? "Fetching the model card from Hugging Face"
      : seconds < 7
        ? "Reading the card for base models and datasets it names"
        : "Matching each name against the lineage graph";

  return (
    <section className="card" aria-labelledby="card-h">
      <div className="card-head">
        <h2 id="card-h">Lineage stated in the model card</h2>
        {result?.source === "saved" && <span className="small muted">Saved copy, Oct 18 2026</span>}
      </div>
      <p className="small muted">
        Hub tags miss lineage that a card states only in prose. Reading the card finds the base models and datasets it
        names, quotes the sentence, and adds each one it can match to the graph. The first read of a card takes about 10
        seconds.
      </p>

      {phase !== "running" && (
        <button className="btn btn-ink" type="button" onClick={run} style={{ marginTop: 12 }}>
          {phase === "done" ? "Read the card again" : "Read the card"}
        </button>
      )}

      {phase === "running" && (
        <div className="progress" role="status" aria-live="polite" style={{ marginTop: 12 }}>
          <span className="spinner" aria-hidden="true" />
          <span>
            {step}. {seconds} s
          </span>
        </div>
      )}

      {phase === "error" && (
        <p className="notice notice--warn" role="status" style={{ marginTop: 12 }}>
          The card could not be read right now. Try again in a moment.
        </p>
      )}

      {phase === "done" && result && (
        <div className="app-stack" style={{ marginTop: 12 }}>
          <div className="verdict-change" aria-label="Verdict before and after reading the card">
            <div>
              <p className="small muted">Before</p>
              <VerdictBadge verdict={result.data.before} large />
            </div>
            <span className="arrow" aria-hidden="true">
              &rarr;
            </span>
            <div>
              <p className="small muted">After</p>
              <VerdictBadge verdict={result.data.after} large />
            </div>
          </div>
          <p className="small">
            {result.data.before === result.data.after
              ? "The verdict is the same after reading the card."
              : `Reading the card changed the verdict from ${result.data.before} to ${result.data.after}.`}{" "}
            {result.data.kept === false
              ? "Shown from this read; the shared graph is left as the Hub tags have it."
              : result.data.edges_written > 0
                ? `${num(result.data.edges_written)} lineage edge${result.data.edges_written === 1 ? "" : "s"} from this card added to the graph.`
                : "No new lineage edges were needed."}
            {result.data.source === "recorded" && result.data.recorded_at
              ? ` The model call was unavailable, so this replays the agent's recorded read of the card from ${new Date(result.data.recorded_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}; the graph writes and the verdict ran live.`
              : ""}
          </p>

          {result.data.claims.length === 0 ? (
            <p>The card names no base model or dataset beyond what the Hub tags already say.</p>
          ) : (
            <ul className="claims">
              {result.data.claims.map((c, i) => {
                const resolved = c.status === "resolved" && c.target;
                const link = resolved ? claimHref(c.kind, c.target!) : null;
                return (
                  <li key={c.kind + c.name + i}>
                    <div className="claim-head">
                      <span className="tier">{KIND[c.kind] ?? c.kind.replace(/_/g, " ")}</span>
                      <span className="mono small break">
                        {link ? (
                          link.internal ? (
                            <Link href={link.href}>{c.name}</Link>
                          ) : (
                            <a href={link.href} target="_blank" rel="noreferrer">
                              {c.name}
                            </a>
                          )
                        ) : (
                          c.name
                        )}
                      </span>
                      <span className={`status status--${resolved ? "ok" : "miss"}`}>
                        {resolved ? "resolved" : c.status}
                      </span>
                    </div>
                    <blockquote className="clause-quote">&ldquo;{plain(c.quote)}&rdquo;</blockquote>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
