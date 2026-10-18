"""Add Dataset nodes and TRAINED_ON edges from the Hub's `dataset:` tags.

Models that train on a dataset but declare no base model are added as Model nodes too.
"""
from pathlib import Path

import duckdb
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
con = duckdb.connect()
con.sql(f"""
CREATE TABLE md AS
SELECT DISTINCT id AS model, substr(unnest(list_filter(tags, t -> starts_with(t, 'dataset:'))), 9) AS dataset
FROM '{RAW / 'models.parquet'}'
""")
con.sql(f"""
CREATE TABLE ds AS
SELECT id, coalesce(substr(list_filter(tags, t -> starts_with(t, 'license:'))[1], 9), '') AS license,
       coalesce(disabled, false) AS disabled, coalesce(gated, 'False') AS gated, coalesce(downloads, 0) AS downloads
FROM '{RAW / 'datasets.parquet'}'
QUALIFY row_number() OVER (PARTITION BY id ORDER BY downloads DESC NULLS LAST) = 1
""")
datasets = con.sql("""
SELECT d.dataset, coalesce(ds.license, ''), coalesce(ds.disabled, false), ds.id IS NULL, coalesce(ds.downloads, 0)
FROM (SELECT DISTINCT dataset FROM md) d LEFT JOIN ds ON ds.id = d.dataset
""").fetchall()
models = con.sql(f"""
SELECT m.id, coalesce(substr(list_filter(m.tags, t -> starts_with(t, 'license:'))[1], 9), ''), coalesce(m.downloads, 0)
FROM '{RAW / 'models.parquet'}' m WHERE m.id IN (SELECT model FROM md)
QUALIFY row_number() OVER (PARTITION BY m.id ORDER BY m.downloads DESC NULLS LAST) = 1
""").fetchall()
edges = con.sql("SELECT model, dataset FROM md").fetchall()

g = FalkorDB(host="localhost", port=int(__import__("os").environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
try:
    g.query("CREATE INDEX FOR (d:Dataset) ON (d.id)")
except Exception as e:
    print("index:", e)
B = 20000
for i in range(0, len(datasets), B):
    g.query("UNWIND $rows AS r MERGE (d:Dataset {id: r[0]}) "
            "SET d.license = r[1], d.disabled = r[2], d.missing = r[3], d.downloads = r[4]",
            {"rows": [list(r) for r in datasets[i:i + B]]}, timeout=600000)
print("datasets", len(datasets))
for i in range(0, len(models), B):
    g.query("UNWIND $rows AS r MERGE (m:Model {id: r[0]}) "
            "ON CREATE SET m.license = r[1], m.downloads = r[2], m.missing = false, m.task = '', m.params = 0, "
            "m.inherits = [], m.clean = false",
            {"rows": [list(r) for r in models[i:i + B]]}, timeout=600000)
print("models touched", len(models))
for i in range(0, len(edges), B):
    g.query("UNWIND $rows AS r MATCH (m:Model) WHERE m.id = r[0] MATCH (d:Dataset) WHERE d.id = r[1] "
            "MERGE (m)-[t:TRAINED_ON]->(d) ON CREATE SET t.source = 'hub tag'",
            {"rows": [list(r) for r in edges[i:i + B]]}, timeout=600000)
    print(f"edges {min(i + B, len(edges))}/{len(edges)}", flush=True)
print(g.query("MATCH (d:Dataset) WHERE d.disabled = true RETURN count(d)").result_set)
