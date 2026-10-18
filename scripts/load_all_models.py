"""Put every Hub model in the graph, with its effective license.

For each of the ~3.16M models: declared license tag, the named license behind
`license: other`, the effective license FinePrint uses, 30-day downloads, task,
own parameter count, languages, and whether the repo ships a license file.
"""
import sys
import time
from pathlib import Path

import duckdb
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import ALIASES  # noqa: E402

RAW = ROOT / "data" / "raw" / "models.parquet"
con = duckdb.connect()
alias_sql = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in ALIASES.items())
rows = con.sql(f"""
WITH base AS (
  SELECT id,
         coalesce(substr(list_filter(tags, t -> starts_with(t, 'license:'))[1], 9), '') AS tag,
         lower(json_extract_string(cardData, '$.license_name')) AS lname,
         coalesce(downloads, 0) AS downloads,
         coalesce(pipeline_tag, '') AS task,
         coalesce(safetensors.total, 0) AS own_params,
         list_filter(tags, t -> len(t) = 2 AND t ~ '^[a-z]{{2}}$') AS langs,
         len(list_filter(siblings, s -> lower(s.rfilename) LIKE 'license%' OR lower(s.rfilename) LIKE '%/license%'
                                    OR lower(s.rfilename) LIKE 'notice%' OR lower(s.rfilename) LIKE '%use_policy%')) > 0 AS has_license_file
  FROM '{RAW}'
  QUALIFY row_number() OVER (PARTITION BY id ORDER BY downloads DESC NULLS LAST) = 1
)
SELECT id, tag, coalesce(lname, ''),
       CASE WHEN tag = 'other' AND lname IS NOT NULL THEN (CASE lname {alias_sql} ELSE lname END) ELSE tag END AS eff,
       downloads, task, own_params, langs, has_license_file
FROM base
""").fetchall()
print("models", len(rows), flush=True)

g = FalkorDB(host="localhost", port=int(__import__("os").environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
try:
    g.query("CREATE CONSTRAINT ON (m:Model) ASSERT m.id IS UNIQUE")
except Exception as e:
    print("constraint:", str(e)[:80])
B = 25000
t0 = time.time()
for i in range(0, len(rows), B):
    g.query(
        """UNWIND $rows AS r
           MERGE (m:Model {id: r[0]})
           ON CREATE SET m.missing = false, m.params = r[6], m.task = r[5], m.inherits = [], m.clean = false
           SET m.license_tag = r[1], m.license_name = r[2], m.license = r[3], m.downloads = r[4],
               m.own_params = r[6], m.languages = r[7], m.has_license_file = r[8]""",
        {"rows": [list(r) for r in rows[i:i + B]]}, timeout=600000,
    )
    if i % 250000 == 0:
        print(f"{i + B}/{len(rows)} {time.time() - t0:.0f}s", flush=True)
print("done", f"{time.time() - t0:.0f}s", g.query("MATCH (m:Model) RETURN count(m)").result_set)
