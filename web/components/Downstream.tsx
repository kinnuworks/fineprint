"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchDescendants } from "@/lib/api";
import { compact, licClass, num } from "@/lib/format";
import type { Descendants, Source } from "@/lib/types";

export default function Downstream({ id }: { id: string }) {
  const [res, setRes] = useState<{ data: Descendants | null; source: Source | "down" | "none" } | null>(null);
  const [all, setAll] = useState(false);

  useEffect(() => {
    let live = true;
    fetchDescendants(id, 50).then((r) => live && setRes(r));
    return () => {
      live = false;
    };
  }, [id]);

  return (
    <section className="card" aria-labelledby="downstream-h">
      <div className="card-head">
        <h2 id="downstream-h">Downstream</h2>
        {res?.source === "saved" && <span className="small muted">Saved copy, Oct 18 2026</span>}
      </div>
      <p className="small muted" style={{ marginBottom: 12 }}>
        Models on the Hub that declare this one as an ancestor.
      </p>
      {!res && (
        <div aria-busy="true">
          <div className="skeleton" style={{ height: 64 }} />
          <div className="skeleton" style={{ height: 120, marginTop: 12 }} />
        </div>
      )}
      {res?.source === "none" && <p>No downstream models are recorded for this model.</p>}
      {res?.source === "down" && <p className="muted">Downstream data is unavailable right now.</p>}
      {res?.data && res.data.stats.count === 0 && <p>No downstream models are recorded for this model.</p>}
      {res?.data && res.data.stats.count > 0 && (
        <>
          <dl className="facts">
            <div>
              <dt>Descendants</dt>
              <dd>{num(res.data.stats.count)}</dd>
            </div>
            <div>
              <dt>Deepest level</dt>
              <dd>{num(res.data.stats.deepest)}</dd>
            </div>
            <div>
              <dt>Their downloads, 30 days</dt>
              <dd>{num(res.data.stats.downloads)}</dd>
            </div>
          </dl>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>License</th>
                  <th className="num">Level</th>
                  <th className="num">Downloads</th>
                </tr>
              </thead>
              <tbody>
                {(all ? res.data.top : res.data.top.slice(0, 10)).map((d) => (
                  <tr key={d.id}>
                    <td className="idcell">
                      <Link href={"/" + d.id.split("/").map(encodeURIComponent).join("/")}>{d.id}</Link>
                    </td>
                    <td>
                      <span className={licClass(d.license)}>{d.license ?? "none"}</span>
                    </td>
                    <td className="num">{d.depth}</td>
                    <td className="num">{compact(d.downloads)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {res.data.top.length > 10 && (
            <button className="btn btn-outline more" type="button" onClick={() => setAll((a) => !a)}>
              {all ? "Show top 10" : `Show top ${res.data.top.length}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
