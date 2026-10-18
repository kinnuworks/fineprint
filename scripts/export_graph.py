"""Export the lineage graph as CSVs for falkordb-bulk-loader.

Keeps every model that has a declared parent or is a declared parent,
plus the License nodes they point to.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "derived"
OUT = ROOT / "data" / "bulk"
OUT.mkdir(parents=True, exist_ok=True)

REL = {
    "finetune": "FINETUNE_OF",
    "adapter": "ADAPTER_OF",
    "merge": "MERGE_OF",
    "quantized": "QUANTIZED_FROM",
}

con = duckdb.connect()
con.sql(f"CREATE VIEW e AS SELECT * FROM '{D / 'edges.parquet'}' WHERE child <> parent")
con.sql(f"CREATE VIEW s AS SELECT * FROM '{D / 'models_slim.parquet'}' QUALIFY row_number() OVER (PARTITION BY id ORDER BY downloads DESC NULLS LAST) = 1")
con.sql("""
CREATE TABLE keep AS
SELECT DISTINCT id FROM (SELECT child AS id FROM e UNION SELECT parent AS id FROM e)
""")
con.sql(f"""
COPY (
  SELECT k.id AS "id:ID(Model)", coalesce(s.license, '') AS "license:STRING",
         coalesce(s.downloads, 0) AS "downloads:INT", coalesce(s.downloadsAllTime, 0) AS "downloads_all:INT",
         (s.id IS NULL) AS "missing:BOOLEAN"
  FROM keep k LEFT JOIN s USING (id)
) TO '{OUT / 'Model.csv'}' (HEADER, DELIMITER ',')
""")
for rel, label in REL.items():
    con.sql(f"""
    COPY (
      SELECT DISTINCT child AS ":START_ID(Model)", parent AS ":END_ID(Model)"
      FROM e WHERE relation = '{rel}'
    ) TO '{OUT / (label + '.csv')}' (HEADER, DELIMITER ',')
    """)
for f in sorted(OUT.glob("*.csv")):
    n = con.sql(f"SELECT count(*) FROM read_csv_auto('{f}')").fetchone()[0]
    print(f.name, n)
