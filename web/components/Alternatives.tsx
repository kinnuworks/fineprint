"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchSubstitutes } from "@/lib/api";
import { compact, licClass } from "@/lib/format";
import type { Source, Substitutes } from "@/lib/types";

function params(n: number | null | undefined): string {
  if (!n) return "n/a";
  return n >= 1e9 ? `${(n / 1e9).toFixed(1)}B` : `${Math.round(n / 1e6)}M`;
}

export default function Alternatives({ id }: { id: string }) {
  const [res, setRes] = useState<{ data: Substitutes | null; source: Source | "down" | "none" } | null>(null);

  useEffect(() => {
    let live = true;
    fetchSubstitutes(id, 5).then((r) => live && setRes(r));
    return () => {
      live = false;
    };
  }, [id]);

  const subs = res?.data?.substitutes ?? [];

  return (
    <section className="card" aria-labelledby="alt-h">
      <div className="card-head">
        <h2 id="alt-h">Clean alternatives of the same task and size</h2>
        {res?.source === "saved" && <span className="small muted">Saved copy, Oct 18 2026</span>}
      </div>
      {res?.data?.task && (
        <p className="small muted">
          Models tagged <code>{res.data.task}</code>
          {res.data.params ? ` near ${params(res.data.params)} parameters` : ""} whose known chain carries no
          restrictive terms.
        </p>
      )}
      {!res && <div className="skeleton" style={{ height: 120 }} aria-busy="true" />}
      {res && subs.length === 0 && (
        <p className="muted">
          {res.source === "down"
            ? "Alternatives are unavailable right now."
            : (res.data?.note ?? "No clean model with the same task and a similar size.")}
        </p>
      )}
      {subs.length > 0 && (
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Model</th>
                <th>License</th>
                <th className="num">Size</th>
                <th className="num">Downloads</th>
              </tr>
            </thead>
            <tbody>
              {subs.map((s) => (
                <tr key={s.id}>
                  <td className="idcell">
                    <Link href={"/" + s.id.split("/").map(encodeURIComponent).join("/")}>{s.id}</Link>
                  </td>
                  <td>
                    <span className={licClass(s.license)}>{s.license ?? "none"}</span>
                  </td>
                  <td className="num">{params(s.params)}</td>
                  <td className="num">{compact(s.downloads_30d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
