"""Connections to FalkorDB, one per database user (see acl.py).

Without the FINEPRINT_* passwords in the environment (local development) every helper falls
back to the single default connection.
"""
import os
import time
from functools import lru_cache

from falkordb import FalkorDB

LINEAGE_TYPES = ["FINETUNE_OF", "ADAPTER_OF", "MERGE_OF", "QUANTIZED_FROM"]


def _connect(username: str | None, password: str | None) -> FalkorDB:
    return FalkorDB(host=os.environ.get("FALKORDB_HOST", "localhost"),
                    port=int(os.environ.get("FALKORDB_PORT", "6379")),
                    username=username or None, password=password or None)


@lru_cache(maxsize=1)
def db():
    """Admin connection: Clerk writes, creating org users, listing graphs."""
    return _connect(os.environ.get("FALKORDB_USERNAME"), os.environ.get("FALKORDB_PASSWORD"))


@lru_cache(maxsize=1)
def ro_db():
    """fp-hub-ro: may only run GRAPH.RO_QUERY on hub and family:*."""
    pw = os.environ.get("FINEPRINT_HUB_RO_PASSWORD")
    return _connect("fp-hub-ro", pw) if pw else db()


@lru_cache(maxsize=1)
def whatif_db():
    """fp-whatif: GRAPH.COPY / QUERY / DELETE on family:* and whatif:*, read-only on hub."""
    pw = os.environ.get("FINEPRINT_WHATIF_PASSWORD")
    return _connect("fp-whatif", pw) if pw else db()


@lru_cache(maxsize=128)
def org_db(slug: str):
    """fp-org-<slug>: its own org:<slug> graph and nothing else. Created on first use."""
    secret = os.environ.get("FINEPRINT_ORG_SECRET")
    if not secret:
        return db()
    from .acl import ensure_org_user
    name, pw = ensure_org_user(db().connection, slug, secret)
    return _connect(name, pw)


@lru_cache(maxsize=1)
def hub():
    """The hub graph on the admin connection, for the writes the Clerk makes."""
    return db().select_graph(os.environ.get("FALKORDB_GRAPH", "hub"))


@lru_cache(maxsize=1)
def hub_ro():
    return ro_db().select_graph(os.environ.get("FALKORDB_GRAPH", "hub"))


def ro(query: str, params: dict | None = None, timeout: int = 30000):
    return hub_ro().ro_query(query, params or {}, timeout=timeout).result_set


_fulltext = {"ready": False, "checked": 0.0}


def fulltext_ready() -> bool:
    """True once the Model.id fulltext index is OPERATIONAL. deploy/start.sh creates it at boot and
    FalkorDB builds it in the background; until then a query would see only part of it."""
    if _fulltext["ready"] or time.time() - _fulltext["checked"] < 30:
        return _fulltext["ready"]
    _fulltext["checked"] = time.time()
    try:
        rows = ro("CALL db.indexes() YIELD label, types, status WHERE label = 'Model' RETURN types, status")
        # While it builds, db.indexes() lists the Model index twice, one row UNDER CONSTRUCTION.
        _fulltext["ready"] = (any("FULLTEXT" in (t.get("id") or []) for t, _ in rows)
                              and all(s == "OPERATIONAL" for _, s in rows))
    except Exception:
        _fulltext["ready"] = False
    return _fulltext["ready"]
