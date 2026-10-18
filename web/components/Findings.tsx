import Link from "next/link";
import { fetchLoadBearing, fetchRelicensePoints } from "@/lib/api";
import { compact, licClass, num } from "@/lib/format";
import { modelHref } from "@/lib/site";

export function FindingsSkeleton() {
  return (
    <div className="grid" aria-busy="true">
      <div className="card table-card">
        <div className="table-card__head">
          <p>Running PageRank and the relicensing query on the graph.</p>
        </div>
        <div className="skeleton" style={{ height: 260, margin: "0 24px 24px" }} />
      </div>
    </div>
  );
}

/** Findings tables. They stream in after the rest of the page, since the relicensing query takes several seconds. */
export default async function Findings() {
  const [lb, rp] = await Promise.all([fetchLoadBearing(10), fetchRelicensePoints(10)]);
  const points = rp.data.relicensing_points;
  const spread = rp.data.points_with_mismatched_descendants ?? rp.data.points_that_spread_to_others;
  const below = rp.data.mismatched_models_below_some_point ?? rp.data.mismatches_inherited_from_someone_else;
  const top = lb.data.top[0];

  return (
    <div className="grid">
      <div className="card table-card">
        <div className="table-card__head">
          <div>
            <h3 className="t-title">The models most of the Hub rests on.</h3>
            <p>
              Ranked by PageRank over the lineage graph.
              {top ? ` The top one, ${top.id}, is under ${top.license}.` : ""} PageRank also counts automated upload
              farms, so compare the downloads of each model&apos;s descendants.
            </p>
          </div>
          {lb.source === "saved" && <span className="chip chip--soft">Saved copy</span>}
        </div>
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th className="rank">#</th>
                <th>Model</th>
                <th>License</th>
                <th className="num">Downloads</th>
                <th className="num">Descendants</th>
                <th className="num">Their downloads</th>
              </tr>
            </thead>
            <tbody>
              {lb.data.top.map((m, i) => (
                <tr key={m.id}>
                  <td className="rank">{i + 1}</td>
                  <td className="idcell">
                    <Link href={modelHref(m.id)}>{m.id}</Link>
                  </td>
                  <td>
                    <span className={licClass(m.license)}>{m.license ?? "none"}</span>
                  </td>
                  <td className="num">{compact(m.downloads_30d)}</td>
                  <td className="num">{m.descendants != null ? num(m.descendants) : "n/a"}</td>
                  <td className="num">{compact(m.descendant_downloads_30d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-card__foot">Downloads over the last 30 days. Their downloads: all descendants combined.</p>
      </div>

      <div className="card table-card">
        <div className="table-card__head">
          <div>
            <h3 className="t-title">Where the declared license changes.</h3>
            <p>
              {num(points)} models declare a permissive license directly below a parent with restricted terms.
              {spread != null && <> {num(spread)} of them have descendants that repeat the difference.</>}
              {below != null && <> {num(below)} models sit below one of these points.</>}
            </p>
          </div>
          {rp.source === "saved" && <span className="chip chip--soft">Saved copy</span>}
        </div>
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Model</th>
                <th>Restricted parent</th>
                <th className="num">Models below</th>
                <th className="num">Their downloads</th>
              </tr>
            </thead>
            <tbody>
              {rp.data.top.map((m) => (
                <tr key={m.model}>
                  <td className="idcell">
                    <Link href={modelHref(m.model)}>{m.model}</Link>
                  </td>
                  <td className="idcell">
                    {(m.restricted_parents ?? m.restricted_parent ?? []).map((p, i) => (
                      <span key={p}>
                        {i > 0 && ", "}
                        <Link href={modelHref(p)}>{p}</Link>
                      </span>
                    ))}
                  </td>
                  <td className="num">{num(m.mismatched_models_below)}</td>
                  <td className="num">{compact(m.their_downloads_30d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-card__foot">
          Models below: descendants whose declared license also differs from upstream terms.
        </p>
      </div>
    </div>
  );
}
