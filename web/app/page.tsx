import Link from "next/link";
import { Suspense } from "react";
import AppIcon from "@/components/AppIcon";
import CheckButton from "@/components/CheckButton";
import Findings, { FindingsSkeleton } from "@/components/Findings";
import HeroMock from "@/components/HeroMock";
import RevealObserver from "@/components/RevealObserver";
import SearchBox from "@/components/SearchBox";
import TryIt, { type Hero } from "@/components/TryIt";
import VerdictBadge, { DecisionBadge } from "@/components/VerdictBadge";
import { fetchStats, fetchWhatIf } from "@/lib/api";
import { savedReadCard, savedReport } from "@/lib/fallback";
import { compact, first, num, pct, relationLabel } from "@/lib/format";
import { AGENT_README, REPO_URL } from "@/lib/site";

const HEROES: Hero[] = [
  { id: "kenpath/svara-tts-v1", label: "svara-tts-v1" },
  { id: "ifmylove2011/girlslike", label: "girlslike (FLUX LoRA)" },
  { id: "unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit", label: "Qwen2.5-3B bnb-4bit" },
  { id: "deepseek-ai/DeepSeek-R1-Distill-Llama-8B", label: "DeepSeek-R1-Distill-Llama-8B" },
  { id: "Qwen/Qwen2.5-7B-Instruct", label: "Qwen2.5-7B-Instruct" },
  { id: "TheBloke/LeoScorpius-GreenNode-Alpaca-7B-v1-GGUF", label: "LeoScorpius Alpaca GGUF" },
];

const short = (id: string) => id.split("/").pop() ?? id;

function Icon({ d }: { d: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const ICONS = {
  lineage: "M6 3v6a3 3 0 0 0 3 3h6a3 3 0 0 1 3 3v6M6 3a2 2 0 1 0 0 .01M18 21a2 2 0 1 0 0-.01M6 9v12",
  card: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4",
  scale: "M12 3v18M5 7h14M5 7l-3 7a4 4 0 0 0 6 0zM19 7l-3 7a4 4 0 0 0 6 0zM8 21h8",
  terminal: "M4 17l6-5-6-5M12 19h8",
};

export default async function Home() {
  const [{ data: s, source }, whatIf] = await Promise.all([fetchStats(), fetchWhatIf()]);

  const n = s.graph_audit?.numbers ?? {};
  const mismatched =
    s.inheriting_but_declare_permissive ??
    first(n.inheriting_but_declare_permissive) ??
    s.of_those_declaring_permissive_license ??
    0;
  const mismatchedDownloads =
    s.their_downloads_30d ?? (n.inheriting_but_declare_permissive as number[] | undefined)?.[1];
  const total = s.models_total ?? first(n.models_total);
  const nonCommercial =
    s.non_commercial_upstream_declare_permissive ?? first(n.non_commercial_upstream_declare_permissive);
  const licenseFile = s.ship_license_file ?? first(n.of_those_ship_license_file);
  const hub = s.hub_api_comparison;
  const unsloth = s.unsloth;

  const ken = savedReport("kenpath/svara-tts-v1", true);
  const kenOne = savedReport("kenpath/svara-tts-v1", false);
  const kenPath = ken?.liens[0]?.paths[0];
  const kenRels = kenPath?.relations ?? [];
  const girl = savedReport("ifmylove2011/girlslike", true, "commercial");
  const girlNc = savedReport("ifmylove2011/girlslike", true, "noncommercial");
  const deep = savedReadCard("deepseek-ai/DeepSeek-R1-Distill-Llama-8B");
  const deepClaims = deep
    ? deep.claims
        .filter((c, i, all) => all.findIndex((x) => x.quote === c.quote) === i)
        .filter((c) => !c.quote.includes("|"))
        .slice(0, 2)
    : [];

  const hubHours = hub ? hub.estimated_sequential_minutes / 60 : null;
  const hubMs = hub ? hub.estimated_sequential_minutes * 60 * 1000 : null;
  const graphMs = hub?.graph_ms_median ?? null;

  return (
    <main>
      <RevealObserver />

      {/* Hero */}
      <section className="hero">
        <div className="container">
          <span className="badge badge--dot">{num(mismatched)} models flagged on the Hub</span>
          <h1>
            Every fine-tune comes with <em className="t-serif">fine print</em>.
          </h1>
          <p className="lead">
            FinePrint walks every ancestor model and training dataset of any Hugging Face model and tells you what you
            agree to when you ship it.
          </p>
          <div className="cta-row">
            <CheckButton />
            <a href="#findings" className="btn btn-outline btn-lg">
              Read the findings
            </a>
          </div>
          <div className="trust">
            <span>Free</span>
            <span>Open source</span>
            <span>Works on any public Hugging Face model</span>
          </div>
          <div id="check" className="search-wrap">
            <SearchBox
              inputId="model-search"
              placeholder="Model id or Hugging Face URL, e.g. meta-llama/Llama-3.1-8B"
              showKbd
            />
            <p className="search__hint">
              Replace <span className="t-mono">huggingface.co</span> with this site&apos;s domain in any model URL to
              open its report.
            </p>
          </div>
          <div className="hero__visual">
            <HeroMock />
          </div>
        </div>
      </section>

      {/* Problem and solution */}
      <section className="section" id="how">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">
              <span className="dot" />
              How it works
            </span>
            <h2>
              The model page shows one hop. <span className="t-muted">The terms come from every hop.</span>
            </h2>
            <p className="lead">
              A Hugging Face model page lists its direct parents. License terms travel further than that: through
              fine-tunes, adapters, quantized builds and merges, back to the original release.
            </p>
          </div>
          <div className="grid grid-2">
            <div className="card card--flat compare-card reveal">
              <span className="eyebrow">Direct parents only</span>
              <p className="t-title">What the model page shows.</p>
              {kenOne && (
                <div className="strip">
                  <span className="strip__node">{short(kenOne.model)}</span>
                  {kenOne.ancestors.map((a) => (
                    <span key={a.id} style={{ display: "contents" }}>
                      <span className="strip__arrow">&rarr;</span>
                      <span className="strip__node">
                        {short(a.id)} <span className="lic lic--permissive">{a.license}</span>
                      </span>
                    </span>
                  ))}
                </div>
              )}
              <div className="result">
                {kenOne && <VerdictBadge verdict={kenOne.verdict} />}
                <span>One hop up, everything is apache-2.0.</span>
              </div>
            </div>
            <div className="card card--chosen compare-card reveal" style={{ "--i": 1 } as React.CSSProperties}>
              <span className="eyebrow">
                <span className="dot" />
                Full lineage
              </span>
              <p className="t-title">What FinePrint shows.</p>
              {kenPath && (
                <div className="strip">
                  {kenPath.models.map((m, i) => (
                    <span key={m} style={{ display: "contents" }}>
                      <span
                        className={`strip__node${kenPath.licenses?.[i] === ken?.liens[0]?.license ? " strip__node--restricted" : ""}`}
                      >
                        {short(m)}
                      </span>
                      {i < kenPath.models.length - 1 && (
                        <span className="strip__arrow">{relationLabel(kenRels[i] ?? "")} &rarr;</span>
                      )}
                    </span>
                  ))}
                </div>
              )}
              <div className="result">
                {ken && <VerdictBadge verdict={ken.verdict} />}
                {ken && <DecisionBadge decision={ken.decision} verdict={ken.verdict} />}
                <span>
                  {ken?.liens[0]?.family} terms {ken?.liens[0]?.depth} hops up. {ken?.why}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Findings */}
      <section className="section" id="findings">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">
              <span className="dot" />
              Findings
            </span>
            <h2>What the whole Hub looks like.</h2>
            <p className="lead">
              Counted in FalkorDB over all {num(total)} public models on Hugging Face, Oct 18 2026.
              {source === "saved" ? " Saved copy." : ""}
            </p>
          </div>

          <div className="bento">
            <div className="span-4 stat-cell reveal">
              <span className="eyebrow">Declared license differs from upstream terms</span>
              <div>
                <div className="big">{num(mismatched)}</div>
                <p className="t-title" style={{ marginTop: 10 }}>
                  models declare a permissive license while inheriting restricted terms.
                </p>
              </div>
              {licenseFile != null && <p>Only {num(licenseFile)} of these ship a license file.</p>}
            </div>
            {nonCommercial != null && (
              <div className="span-2 stat-cell reveal" style={{ "--i": 1 } as React.CSSProperties}>
                <span className="eyebrow">Non-commercial upstream</span>
                <div className="big big--sm">{num(nonCommercial)}</div>
                <p>
                  declare a permissive license while an ancestor&apos;s license is non-commercial
                  {s.non_commercial_downloads_30d != null
                    ? `, with ${compact(s.non_commercial_downloads_30d)} downloads in 30 days.`
                    : "."}
                </p>
              </div>
            )}
            {mismatchedDownloads != null && (
              <div className="span-2 stat-cell reveal">
                <span className="eyebrow">Downloads</span>
                <div className="big big--sm">{compact(mismatchedDownloads)}</div>
                <p>downloads in the last 30 days of the {num(mismatched)} models above.</p>
              </div>
            )}
            {unsloth && (
              <div className="span-2 stat-cell reveal" style={{ "--i": 1 } as React.CSSProperties}>
                <span className="eyebrow">One card template</span>
                <div className="big big--sm">{num(unsloth.template_signature)}</div>
                <p>
                  of them ({pct(unsloth.template_share, 0)}) carry the tags Unsloth&apos;s model card template writes,
                  which include license: apache-2.0 whatever the base model is.
                </p>
              </div>
            )}
            {whatIf && (
              <div className="span-2 stat-cell reveal" style={{ "--i": 2 } as React.CSSProperties}>
                <span className="eyebrow">What if</span>
                <div className="big big--sm">
                  {num(whatIf.still_non_commercial_after)}
                  <span className="t-small" style={{ marginLeft: 8 }}>
                    of {num(whatIf.family_models)}
                  </span>
                </div>
                <p>
                  FLUX.1-dev family models would still be non-commercial if FLUX.1-dev were relicensed as Apache-2.0,
                  because LoRAs and fine-tunes declare its license themselves.
                </p>
              </div>
            )}
            {hub && hubHours != null && hubMs != null && graphMs != null && (
              <div className="span-6 stat-cell reveal" style={{ minHeight: 0 }}>
                <div>
                  <span className="eyebrow">Why a graph</span>
                  <p className="t-title" style={{ marginTop: 10 }}>
                    Every descendant of {hub.root}: {num(hub.hub_api_calls_needed)} Hub API calls, or one graph query.
                  </p>
                </div>
                <div className="race" aria-label="Time to list every descendant">
                  <div className="race__row">
                    <span>Hub API, one call at a time</span>
                    <span className="race__bar">
                      <span style={{ width: "100%" }} />
                    </span>
                    <span className="t-mono">about {hubHours.toFixed(1)} h</span>
                  </div>
                  <div className="race__row">
                    <span>FalkorDB graph</span>
                    <span className="race__bar race__bar--graph">
                      <span style={{ width: `${Math.max(0.8, (graphMs / hubMs) * 100)}%` }} />
                    </span>
                    <span className="t-mono">{Math.round(graphMs)} ms</span>
                  </div>
                </div>
                <p>
                  {num(hub.descendants)} descendants at a median {hub.median_call_seconds.toFixed(2)} s per Hub call,
                  against the median graph query time.
                </p>
              </div>
            )}
          </div>

          <div style={{ marginTop: 16 }}>
            <Suspense fallback={<FindingsSkeleton />}>
              <Findings />
            </Suspense>
          </div>
        </div>
      </section>

      {/* Feature deep-dives */}
      <section className="section">
        <div className="container stack">
          <div className="split">
            <div>
              <span className="eyebrow">
                <Icon d={ICONS.lineage} />
                Lineage walk
              </span>
              <h3>Every ancestor, in one query.</h3>
              <p className="lead">
                FinePrint keeps Hub lineage in a FalkorDB graph. A report walks finetunes, adapters, quantized builds,
                merges and training datasets back to the original license, and lists every path a term takes.
              </p>
              <div className="chips">
                {["finetune", "adapter", "quantized", "merge", "trained on"].map((c) => (
                  <span key={c} className="chip">
                    {c}
                  </span>
                ))}
              </div>
            </div>
            <div className="split__visual">
              <div className="stage stage--soft" aria-hidden="true">
                <div className="window mini-window">
                  <div className="window__bar">
                    <span className="lights">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="window__title">Proof path</span>
                  </div>
                  <div className="mini">
                    {kenPath && (
                      <div className="tree">
                        {kenPath.models.map((m, i) => (
                          <div className="tree__level" key={m}>
                            <span
                              className={`strip__node${kenPath.licenses?.[i] === ken?.liens[0]?.license ? " strip__node--restricted" : ""}`}
                            >
                              {m}
                            </span>
                            <span
                              className={`lic lic--${kenPath.licenses?.[i] === ken?.liens[0]?.license ? "restricted" : "permissive"}`}
                            >
                              {kenPath.licenses?.[i]}
                            </span>
                            {i < kenPath.models.length - 1 && (
                              <span className="strip__arrow">&darr; {relationLabel(kenRels[i] ?? "")} of</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="split split--flip">
            <div>
              <span className="eyebrow">
                <Icon d={ICONS.card} />
                Card reader
              </span>
              <h3>Reads what the Hub tags leave out.</h3>
              <p className="lead">
                DeepSeek-R1-Distill-Llama-8B declares MIT and names no base model, so the graph alone says UNKNOWN. Its
                card says it is derived from Llama 3.1 8B. The card reader quotes that sentence, resolves it to
                meta-llama/Llama-3.1-8B, and the verdict becomes CLOUDED.
              </p>
              <p className="t-small">
                In a manual check, 41 of 48 lineage edges it proposed were correct. It finds datasets too: the
                LeoScorpius Alpaca GGUF card names tatsu-lab/alpaca, which is CC BY-NC.
              </p>
            </div>
            <div className="split__visual">
              <div className="stage stage--soft" aria-hidden="true">
                <div className="window mini-window">
                  <div className="window__bar">
                    <span className="lights">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="window__title">Read the card</span>
                  </div>
                  <div className="mini" style={{ display: "grid", gap: 12 }}>
                    <p className="mock__id">deepseek-ai/DeepSeek-R1-Distill-Llama-8B</p>
                    {deep && (
                      <div className="ba">
                        <VerdictBadge verdict={deep.before} />
                        <span className="strip__arrow">&rarr;</span>
                        <VerdictBadge verdict={deep.after} />
                      </div>
                    )}
                    <ul className="claims-mini">
                      {deepClaims.map((c) => (
                        <li key={c.quote}>
                          <span className="status status--ok">resolved</span> <span className="t-mono">{c.target}</span>
                          <q>{c.quote.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")}</q>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="split">
            <div>
              <span className="eyebrow">
                <Icon d={ICONS.scale} />
                Decisions
              </span>
              <h3>A decision for the use you have in mind.</h3>
              <p className="lead">
                Each report ends in ALLOW, CONDITIONS or BLOCK, for commercial or non-commercial use, with a one-line
                reason and the clause text behind it.
              </p>
              <p className="t-small">
                ifmylove2011/girlslike is a FLUX.1 [dev] LoRA that declares apache-2.0. Its base model&apos;s license is
                non-commercial.
              </p>
            </div>
            <div className="split__visual">
              <div className="stage stage--soft" aria-hidden="true">
                <div className="window mini-window">
                  <div className="window__bar">
                    <span className="lights">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="window__title">ifmylove2011/girlslike</span>
                  </div>
                  <div className="mini">
                    <div className="segmented" style={{ pointerEvents: "none" }}>
                      <button type="button" aria-pressed="true" tabIndex={-1}>
                        Commercial
                      </button>
                      <button type="button" aria-pressed="false" tabIndex={-1}>
                        Non-commercial
                      </button>
                    </div>
                    <div className="use-grid">
                      {[
                        ["Commercial use", girl],
                        ["Non-commercial use", girlNc],
                      ].map(([label, r]) =>
                        r && typeof r !== "string" ? (
                          <div key={label as string}>
                            <span className="mock__label">{label as string}</span>
                            <div style={{ marginTop: 8 }}>
                              <DecisionBadge decision={r.decision} verdict={r.verdict} />
                            </div>
                            <p>{r.why}</p>
                          </div>
                        ) : null,
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="split split--flip" id="agents">
            <div>
              <span className="eyebrow">
                <Icon d={ICONS.terminal} />
                For coding agents
              </span>
              <h3>Checks before the weights download.</h3>
              <p className="lead">
                The same answers are available to code. An MCP server gives a coding agent a check_model tool,{" "}
                <span className="t-mono">fineprint check</span> fails CI with exit 1 on a BLOCK model, and{" "}
                <span className="t-mono">fineprint.guard()</span> checks every Hugging Face download first.
              </p>
              <div className="chips">
                <span className="chip">MCP server</span>
                <span className="chip">fineprint check in CI</span>
                <span className="chip">Download guard</span>
              </div>
              <p className="t-small" style={{ marginTop: 18 }}>
                <a className="link" href={AGENT_README} target="_blank" rel="noreferrer">
                  Setup and examples in agent/README.md
                </a>
              </p>
            </div>
            <div className="split__visual">
              <div className="stage stage--soft" aria-hidden="true">
                <div className="window window--dark">
                  <div className="window__bar">
                    <span className="lights">
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="window__title">Terminal</span>
                  </div>
                  <pre className="code">
                    <span className="c">$</span> <span className="b">fineprint check demo</span>
                    {"\n"}## FinePrint check: 1 model in demo,
                    {"\n"}## commercial use
                    {"\n"}
                    {"\n"}unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit
                    {"\n"} <span className="r">BLOCK</span> <span className="c">Qwen Research terms upstream</span>
                    {"\n"}
                    {"\n"}Result: fail.
                    {"\n"}
                    <span className="c">$</span> echo $?
                    {"\n"}
                    <span className="r">1</span>
                    {"\n"}
                    {"\n"}
                    <span className="c">&gt;&gt;&gt;</span> import fineprint
                    {"\n"}
                    <span className="c">&gt;&gt;&gt;</span> fineprint.guard(<span className="g">&quot;block&quot;</span>
                    ){"\n"}
                    <span className="c"># BLOCK models now raise FinePrintBlocked</span>
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Try it here */}
      <section className="section" id="try">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">
              <span className="dot" />
              Try it here
            </span>
            <h2>Pick a model and read its fine print.</h2>
          </div>
          <TryIt heroes={HEROES} />
        </div>
      </section>

      {/* FAQ */}
      <section className="section" id="faq">
        <div className="container">
          <div className="section-head">
            <h2>Questions people ask.</h2>
          </div>
          <div className="faq">
            <details>
              <summary>Is this legal advice?</summary>
              <p>
                No. FinePrint shows what the licenses upstream of a model say, with the clause text and a link to the
                source. Whether a term applies to you depends on your use and where you are, which is a question for a
                lawyer.
              </p>
            </details>
            <details>
              <summary>Where does the data come from?</summary>
              <p>
                Lineage and licenses come from Hugging Face Hub metadata: the cfahlgren1/hub-stats daily dump
                (Apache-2.0), loaded into FalkorDB, plus live Hub lookups for models the dump does not have. Clause text
                comes from each license&apos;s own published text, linked on every clause.
              </p>
            </details>
            <details>
              <summary>What does UNKNOWN mean?</summary>
              <p>
                FinePrint could not reach a finding. The model may not be on the Hub, may have been deleted, may name no
                base model, or may use a license that is not in the library yet. The decision then reads Review first,
                and the model should be treated as unchecked.
              </p>
            </details>
            <details>
              <summary>How does the card reader work, and how accurate is it?</summary>
              <p>
                It reads the model card text, picks out the base models and datasets the card names, quotes the sentence
                for each, and matches every name against the graph. Names it cannot match are listed as not in graph. In
                a manual check, 41 of 48 edges it proposed were correct.
              </p>
            </details>
            <details>
              <summary>How do I use it in CI?</summary>
              <p>
                Run <span className="t-mono">fineprint check</span> in your pipeline. It finds model ids in code and
                config files and exits 1 when any model is BLOCK for the use you set. The agent README has a GitHub
                Actions example and a pre-run hook.
              </p>
            </details>
            <details>
              <summary>What does the evaluation show?</summary>
              <p>
                On a sealed set of 69 models whose upstream terms are restricted, FinePrint said clean for none of them.
                A language model reading only the card said clean for 8, direct parents only for 19, and the declared
                license alone for 33.
              </p>
            </details>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="section final">
        <div className="container">
          <AppIcon className="app-icon app-icon--lg" />
          <h2>
            Check a model before you ship it. <span className="t-muted">It takes one URL.</span>
          </h2>
          <div className="cta-row">
            <CheckButton />
            <a href={REPO_URL} className="btn btn-outline btn-lg" target="_blank" rel="noreferrer">
              View the source
            </a>
          </div>
          <p className="t-small" style={{ marginTop: 18 }}>
            Or open a report directly:{" "}
            <Link className="link t-mono" href="/kenpath/svara-tts-v1">
              /kenpath/svara-tts-v1
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
