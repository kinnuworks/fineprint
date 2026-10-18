# Findings

The current numbers, the scripts that produce them and their output files are listed in [../CLAIMS.md](../CLAIMS.md). The headline counts are computed in FalkorDB by `scripts/headline_graph.py` and saved with their Cypher text in `data/derived/headline_graph.json`.

An earlier pass computed the same kind of numbers in DuckDB from the dump, covering only Llama, Gemma and CC BY-NC (176,002 models inheriting restricted terms, 39,848 declaring a permissive license). It is kept as a cross-check under `duckdb_cross_check` in `GET /api/stats` and in `data/derived/headline.json`.

The 40-card spot check from that pass is in `data/handcheck/` (38 of 40 matched the dump; two cards had no license line).
