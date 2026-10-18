"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { FalkorDBCanvas, Data, GraphNode } from "@falkordb/canvas";
import { hopRelations, licClass, licenseClass, midTrim, relationLabel, type LicenseClass } from "@/lib/format";
import type { Report } from "@/lib/types";

export interface ChainNode {
  num: number;
  id: string;
  license: string | null;
  depth: number;
  cls: LicenseClass;
  target: boolean;
  dataset: boolean;
}

interface ChainEdge {
  source: number;
  target: number;
  relation: string;
  inferred: boolean;
}

/**
 * Builds the chain of title (model, ancestors, datasets) from a report.
 * Edges come from each ancestor's child -[relation]-> id record and from every
 * lien proof path, so parallel relations between the same two models are kept.
 */
export function buildChain(report: Report): { nodes: ChainNode[]; edges: ChainEdge[] } {
  const restrictive = new Set(report.liens.map((l) => l.license.toLowerCase()));
  const byId = new Map<string, ChainNode>();
  const add = (id: string, license: string | null, depth: number, target = false) => {
    const existing = byId.get(id);
    if (existing) {
      if (existing.license == null && license != null) {
        existing.license = license;
        existing.cls = licenseClass(license, restrictive);
      }
      existing.depth = Math.min(existing.depth, depth);
      return existing;
    }
    const node: ChainNode = {
      num: byId.size + 1,
      id,
      license,
      depth,
      cls: licenseClass(license, restrictive),
      target,
      dataset: false,
    };
    byId.set(id, node);
    return node;
  };

  const edges = new Map<string, ChainEdge>();
  const link = (from: ChainNode, to: ChainNode, relation: string, inferred = false) => {
    const key = `${from.num}>${to.num}>${relation}`;
    if (!edges.has(key)) edges.set(key, { source: from.num, target: to.num, relation, inferred });
  };

  const root = add(report.model, report.declared_license ?? null, 0, true);
  for (const a of report.ancestors) add(a.id, a.license, a.depth);
  for (const a of report.ancestors) {
    if (!a.child || !a.relation) continue;
    const child = byId.get(a.child) ?? add(a.child, null, Math.max(a.depth - 1, 0));
    link(child, byId.get(a.id)!, relationLabel(a.relation));
  }

  for (const lien of report.liens) {
    for (const p of lien.paths) {
      const rels = hopRelations(p);
      p.models.forEach((m, i) => add(m, p.licenses?.[i] ?? (m === lien.via ? lien.license : null), i));
      for (let i = 0; i < p.models.length - 1; i++) {
        const to = byId.get(p.models[i + 1])!;
        if (rels[i] === "TRAINED_ON") to.dataset = true;
        link(byId.get(p.models[i])!, to, rels[i] ? relationLabel(rels[i]) : "stated in card");
      }
    }
  }

  for (const d of report.datasets ?? []) {
    const from = byId.get(d.model) ?? add(d.model, null, 1);
    const ds = add(d.dataset, d.license || null, from.depth + 1);
    ds.dataset = true;
    link(from, ds, "trained on", Boolean(d.missing));
  }

  // Older API responses gave only an ancestor's depth, not its child. Those
  // ancestors are linked to the model with a dashed line.
  const reached = new Set<number>([root.num]);
  edges.forEach((e) => reached.add(e.target));
  byId.forEach((n) => {
    if (reached.has(n.num)) return;
    link(root, n, n.depth === 1 ? "parent" : `${n.depth} levels up`, true);
  });

  return { nodes: [...byId.values()], edges: [...edges.values()] };
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888888";
}

/** Graph label: the name alone on wide screens, org/…end on narrow ones, both cut in the middle. */
function shortName(id: string, narrow: boolean): string {
  if (narrow) return midTrim(id, 22);
  const name = id.includes("/") ? id.split("/").slice(1).join("/") : id;
  return name.length > 28 ? name.slice(0, 13) + "…" + name.slice(-13) : name;
}

export default function LineageGraph({ report }: { report: Report }) {
  const router = useRouter();
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<FalkorDBCanvas | null>(null);
  const fitRef = useRef<(() => void) | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [focus, setFocus] = useState<ChainNode | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const chain = useMemo(() => buildChain(report), [report]);
  const levels = useMemo(() => Math.max(...chain.nodes.map((n) => n.depth)) + 1, [chain]);
  const nodesByNum = useMemo(() => new Map(chain.nodes.map((n) => [n.num, n])), [chain]);

  // Mount the canvas element once.
  useEffect(() => {
    let cancelled = false;
    const host = hostRef.current;
    if (!host) return;
    import("@falkordb/canvas")
      .then(() => {
        if (cancelled) return;
        const el = document.createElement("falkordb-canvas") as FalkorDBCanvas;
        el.style.display = "block";
        el.style.width = "100%";
        el.style.height = "100%";
        host.appendChild(el);
        canvasRef.current = el;
        setState("ready");
      })
      .catch(() => !cancelled && setState("error"));

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onTheme = () => setThemeTick((t) => t + 1);
    mq.addEventListener("change", onTheme);
    return () => {
      cancelled = true;
      mq.removeEventListener("change", onTheme);
      canvasRef.current?.remove();
      canvasRef.current = null;
    };
  }, []);

  // Push config and data whenever the report or theme changes.
  useEffect(() => {
    const el = canvasRef.current;
    const host = hostRef.current;
    if (state !== "ready" || !el || !host) return;
    let fitTimer: ReturnType<typeof setTimeout> | undefined;
    let lateFit: ReturnType<typeof setTimeout> | undefined;
    let lastFit: ReturnType<typeof setTimeout> | undefined;
    let observer: ResizeObserver | undefined;
    try {
      const colors: Record<LicenseClass, string> = {
        restrictive: cssVar("--lic-restricted"),
        permissive: cssVar("--lic-permissive"),
        unknown: cssVar("--lic-unknown"),
      };
      const edgeColor = cssVar("--ink-4");
      const textColor = cssVar("--ink");
      const mutedColor = cssVar("--ink-3");
      const narrow = host.clientWidth < 600;
      el.setConfig({
        backgroundColor: cssVar("--surface"),
        foregroundColor: cssVar("--ink"),
        layoutMode: "tree",
        layoutOptions: {
          tree: { direction: narrow ? "td" : "lr", levelDistance: narrow ? 130 : 150, nodeSpacing: 70 },
        },
        captionsKeys: [["label", true]],
        nodeStyle: { fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif' },
        node: {
          // Labels go under the node so long model names stay readable.
          nodeCanvasObject: (node: GraphNode, ctx: CanvasRenderingContext2D) => {
            const x = node.x ?? 0;
            const y = node.y ?? 0;
            const n = nodesByNum.get(node.id);
            ctx.beginPath();
            if (n?.dataset) {
              const r = node.size * 0.9;
              ctx.roundRect(x - r, y - r, 2 * r, 2 * r, 3);
            } else {
              ctx.arc(x, y, node.size, 0, 2 * Math.PI);
            }
            ctx.fillStyle = node.color;
            ctx.fill();
            if (n?.target) {
              ctx.lineWidth = 2;
              ctx.strokeStyle = textColor;
              ctx.stroke();
            }
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = textColor;
            ctx.font = `${n?.target ? 600 : 400} 8px "Plus Jakarta Sans", system-ui, sans-serif`;
            ctx.fillText(String((node.data as { label?: string }).label ?? ""), x, y + node.size + 3);
            ctx.fillStyle = mutedColor;
            ctx.font = '400 6px "Geist Mono", ui-monospace, monospace';
            ctx.fillText(String((node.data as { license?: string }).license ?? ""), x, y + node.size + 13);
          },
          nodePointerAreaPaint: (node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, node.size + 2, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
          },
        },
        linkStyle: { fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif' },
        linkLineDash: (link) => ((link.data as { inferred?: boolean })?.inferred ? [3, 3] : []),
        eventHandlers: {
          // The canvas runs its own zoom-to-fit when the layout settles; refit after it so labels stay inside.
          onEngineStop: () => {
            clearTimeout(fitTimer);
            fitTimer = setTimeout(() => fitRef.current?.(), 60);
          },
          onNodeHover: (node: GraphNode | null) => {
            if (node) setFocus(nodesByNum.get(node.id) ?? null);
          },
          onNodeClick: (node: GraphNode) => {
            const n = nodesByNum.get(node.id);
            if (n) setFocus(n);
          },
        },
      });
      const data: Data = {
        nodes: chain.nodes.map((n) => ({
          id: n.num,
          labels: [n.cls],
          color: colors[n.cls],
          visible: true,
          size: n.target ? 16 : 12,
          data: { label: shortName(n.id, narrow), id: n.id, license: n.license ?? "none declared" },
        })),
        links: chain.edges.map((e, i) => ({
          id: i + 1,
          relationship: e.relation,
          color: edgeColor,
          source: e.source,
          target: e.target,
          visible: true,
          data: { inferred: e.inferred },
        })),
      };
      el.setData(data);

      // Fit the chain to the box once the layout has positions, and again when the box resizes.
      const fit = () => {
        const nodes = el.getGraphData().nodes;
        const w = host.clientWidth;
        const h = host.clientHeight;
        if (!nodes.length || !w || !h) return;
        // Labels are centred under each node, so a node's reach is half its label's width.
        const half = (n: GraphNode) => {
          const label = String((n.data as { label?: string })?.label ?? "");
          return Math.max(n.size ?? 12, label.length * 2.3) + 6;
        };
        const lefts = nodes.map((n) => (n.x ?? 0) - half(n));
        const rights = nodes.map((n) => (n.x ?? 0) + half(n));
        const ys = nodes.map((n) => n.y ?? 0);
        const [minX, maxX, minY, maxY] = [Math.min(...lefts), Math.max(...rights), Math.min(...ys), Math.max(...ys)];
        const k = Math.max(
          0.3,
          Math.min(nodes.length === 1 ? 1.6 : 3, w / (maxX - minX + 24), h / (maxY - minY + 90)),
        );
        el.getGraph()?.centerAt((minX + maxX) / 2, (minY + maxY) / 2 + 8);
        el.zoom(k);
      };
      fitRef.current = fit;
      // The canvas runs its own fit shortly after setData; fit again after it settles.
      fitTimer = setTimeout(fit, 250);
      lateFit = setTimeout(fit, 900);
      lastFit = setTimeout(fit, 2000);
      observer = new ResizeObserver(() => {
        clearTimeout(fitTimer);
        fitTimer = setTimeout(fit, 150);
      });
      observer.observe(host);
    } catch {
      queueMicrotask(() => setState("error"));
    }
    return () => {
      clearTimeout(fitTimer);
      clearTimeout(lateFit);
      clearTimeout(lastFit);
      fitRef.current = null;
      observer?.disconnect();
    };
  }, [state, chain, nodesByNum, themeTick]);

  return (
    <div>
      <div
        className="graph-box"
        ref={hostRef}
        style={{ "--levels": levels } as React.CSSProperties}
        aria-label={`Chain of title for ${report.model}`}
        role="img"
      >
        {state === "loading" && <div className="graph-msg">Drawing the chain of title</div>}
        {state === "error" && (
          <div className="graph-msg">The graph view could not load. The proof paths below list the same chain.</div>
        )}
      </div>
      <div>
        <ul className="legend">
          <li>
            <span className="dot dot--restricted" /> restrictive terms
          </li>
          <li>
            <span className="dot dot--permissive" /> permissive license
          </li>
          <li>
            <span className="dot dot--unknown" /> unknown or other
          </li>
          <li>
            <span className="sq" /> dataset
          </li>
          <li>Outlined node: this model.</li>
          {chain.edges.some((e) => e.inferred) && (
            <li>Dashed edge: relation not returned, or dataset not found on the Hub.</li>
          )}
        </ul>
        <p className="small muted break" style={{ marginTop: 8 }} aria-live="polite">
          {focus ? (
            <>
              {focus.dataset ? "Dataset " : ""}
              <code>{focus.id}</code> {focus.dataset ? "is licensed" : "declares"}{" "}
              <span className={licClass(focus.license)}>{focus.license ?? "no license"}</span>
              {focus.depth > 0 ? `, ${focus.depth} level${focus.depth > 1 ? "s" : ""} up. ` : ". "}
              {focus.dataset ? (
                <a href={`https://huggingface.co/datasets/${focus.id}`} target="_blank" rel="noreferrer">
                  Open the dataset on Hugging Face
                </a>
              ) : (
                !focus.target && (
                  <a
                    href={"/" + focus.id}
                    onClick={(e) => {
                      e.preventDefault();
                      router.push("/" + focus.id.split("/").map(encodeURIComponent).join("/"));
                    }}
                  >
                    Open its report
                  </a>
                )
              )}
            </>
          ) : (
            "Hover or tap a node for its id and license."
          )}
        </p>
      </div>
    </div>
  );
}
