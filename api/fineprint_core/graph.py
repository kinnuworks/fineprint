"""Read-only access to the lineage graph."""
import os
from functools import lru_cache

from falkordb import FalkorDB

LINEAGE_TYPES = ["FINETUNE_OF", "ADAPTER_OF", "MERGE_OF", "QUANTIZED_FROM"]


@lru_cache(maxsize=1)
def db():
    return FalkorDB(host=os.environ.get("FALKORDB_HOST", "localhost"),
                    port=int(os.environ.get("FALKORDB_PORT", "6379")),
                    password=os.environ.get("FALKORDB_PASSWORD") or None)


@lru_cache(maxsize=1)
def hub():
    return db().select_graph(os.environ.get("FALKORDB_GRAPH", "hub"))


def ro(query: str, params: dict | None = None, timeout: int = 30000):
    return hub().ro_query(query, params or {}, timeout=timeout).result_set
