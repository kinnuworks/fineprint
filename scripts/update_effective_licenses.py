"""Recompute the effective license for models whose tag is empty or `other` and whose card names a license."""
import os
import sys
import time
from pathlib import Path

import duckdb
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import effective  # noqa: E402

rows = duckdb.sql(f"""
SELECT id, coalesce(substr(list_filter(tags, t -> starts_with(t, 'license:'))[1], 9), '') AS tag,
       json_extract_string(cardData, '$.license_name') AS lname
FROM '{ROOT / 'data' / 'raw' / 'models.parquet'}'
WHERE json_extract_string(cardData, '$.license_name') IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY id ORDER BY downloads DESC NULLS LAST) = 1
""").fetchall()
upd = [[mid, effective(tag, lname)] for mid, tag, lname in rows if tag in ("", "other")]
g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
t = time.time()
for i in range(0, len(upd), 25000):
    g.query("UNWIND $rows AS r MATCH (m:Model) WHERE m.id = r[0] SET m.license = r[1]", {"rows": upd[i:i + 25000]}, timeout=590000)
print(f"updated {len(upd)} models in {time.time() - t:.1f}s")
