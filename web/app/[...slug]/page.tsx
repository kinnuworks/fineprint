import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ReportView from "@/components/ReportView";
import { RULESET_RE, fetchReport } from "@/lib/api";
import { HUB_TAILS } from "@/lib/format";
import type { Use } from "@/lib/types";

type Params = Promise<{ slug: string[] }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const NON_MODEL = new Set([
  "datasets",
  "spaces",
  "docs",
  "blog",
  "papers",
  "collections",
  "organizations",
  "settings",
  "api",
]);

function safeDecode(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

/**
 * Maps the URL path to a model id. This is the URL swap:
 * huggingface.co/meta-llama/Llama-3.1-8B becomes /meta-llama/Llama-3.1-8B here.
 * Trailing Hub paths such as /tree/main are ignored.
 */
function toId(slug: string[]): string | null {
  const parts = slug.map(safeDecode).filter(Boolean);
  if (parts.length === 0 || NON_MODEL.has(parts[0])) return null;
  if (parts.length === 1 || HUB_TAILS.has(parts[1])) return parts[0];
  return `${parts[0]}/${parts[1]}`;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const id = toId((await params).slug);
  return { title: id ?? "Not a model" };
}

export default async function ModelPage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { slug } = await params;
  const id = toId(slug);
  if (!id) notFound();
  const sp = await searchParams;
  const graph = sp.graph !== "false" && sp.graph !== "0" && sp.graph !== "off";
  const use: Use = sp.use === "noncommercial" ? "noncommercial" : "commercial";
  const rs = typeof sp.ruleset === "string" && RULESET_RE.test(sp.ruleset) ? sp.ruleset : "";
  const initial = await fetchReport(id, graph, use, rs);

  return (
    <main className="app">
      <div className="container">
        <ReportView
          key={id}
          id={id}
          initial={initial}
          initialGraph={graph}
          initialUse={use}
          initialRuleset={rs}
          hasOrg={id.includes("/")}
        />
      </div>
    </main>
  );
}
