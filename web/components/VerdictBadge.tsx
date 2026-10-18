import { decisionView, verdictKey } from "@/lib/format";

export default function VerdictBadge({ verdict, large = false }: { verdict: string; large?: boolean }) {
  return <span className={`vbadge vbadge--${verdictKey(verdict)}${large ? " vbadge--lg" : ""}`}>{verdict}</span>;
}

/** Decision badge. An UNKNOWN verdict shows "Review first" in the conditions colour. */
export function DecisionBadge({
  decision,
  verdict,
  large = false,
}: {
  decision?: string;
  verdict: string;
  large?: boolean;
}) {
  const v = decisionView(decision, verdict);
  if (!v) return null;
  return (
    <span className={`vbadge vbadge--${v.key}${large ? " vbadge--lg" : ""}`} title={v.hint}>
      {v.label}
    </span>
  );
}
