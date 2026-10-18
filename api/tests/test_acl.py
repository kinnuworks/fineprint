"""Tenant isolation enforced by FalkorDB ACL users. Needs FalkorDB with the hub graph.

Creates throwaway users and graphs, and removes them afterwards.
"""
import secrets
import uuid

import pytest
from redis.exceptions import NoPermissionError, ResponseError

from fineprint_core import acl, graph, rulings
from fineprint_core.graph import _connect, db

HUB_WRITE = "MATCH (m:Model) WHERE m.id = 'meta-llama/Llama-3.2-1B' SET m.acl_probe = 1"


@pytest.fixture(scope="module")
def users():
    admin = db().connection
    a, b = "t-" + uuid.uuid4().hex[:8], "t-" + uuid.uuid4().hex[:8]
    secret = secrets.token_hex(16)
    pw_ro, pw_wi = secrets.token_hex(16), secrets.token_hex(16)
    acl.set_user(admin, "t-hub-ro", pw_ro, acl.rules_hub_ro())
    acl.set_user(admin, "t-whatif", pw_wi, acl.rules_whatif())
    made = {s: acl.ensure_org_user(admin, s, secret) for s in (a, b)}
    db().select_graph(f"org:{b}").query("CREATE (:Ruling {id: 'secret-of-b'})")
    yield {"a": a, "b": b, "ro": _connect("t-hub-ro", pw_ro), "whatif": _connect("t-whatif", pw_wi),
           "org": {s: _connect(*made[s]) for s in made}}
    for s in (a, b):
        try:
            db().select_graph(f"org:{s}").delete()
        except ResponseError:
            pass
    admin.execute_command("ACL", "DELUSER", "t-hub-ro", "t-whatif", *(acl.org_user(s) for s in (a, b)))
    assert db().select_graph("hub").ro_query("MATCH (m:Model) WHERE m.acl_probe = 1 RETURN count(m)").result_set[0][0] == 0


def test_org_user_writes_its_own_graph(users):
    g = users["org"][users["a"]].select_graph(f"org:{users['a']}")
    assert g.query("CREATE (:Ruling {id: 'mine'}) RETURN 1").result_set == [[1]]


def test_org_user_cannot_write_hub(users):
    with pytest.raises(NoPermissionError, match="No permissions to access a key"):
        users["org"][users["a"]].select_graph("hub").query(HUB_WRITE)


def test_org_user_cannot_read_another_org(users):
    with pytest.raises(NoPermissionError, match="No permissions to access a key"):
        users["org"][users["a"]].select_graph(f"org:{users['b']}").ro_query("MATCH (r:Ruling) RETURN r.id")
    with pytest.raises(NoPermissionError):
        users["org"][users["a"]].select_graph(f"org:{users['b']}").delete()


def test_hub_ro_reads_but_cannot_write(users):
    g = users["ro"].select_graph("hub")
    node = g.ro_query("MATCH (m:Model) WHERE m.id = 'meta-llama/Llama-3.2-1B' RETURN m").result_set[0][0]
    assert node.properties["license"] == "llama3.2"
    with pytest.raises(NoPermissionError, match="graph.QUERY"):
        g.query(HUB_WRITE)
    with pytest.raises(NoPermissionError):
        users["ro"].select_graph(f"org:{users['b']}").ro_query("MATCH (r) RETURN r")


def test_whatif_user_copies_families_but_only_reads_hub(users):
    d = users["whatif"]
    fam = graph.db().list_graphs()
    fam = next(g for g in fam if g.startswith("family:"))
    copy = "whatif:t-" + uuid.uuid4().hex[:8]
    d.connection.execute_command("GRAPH.COPY", fam, copy)
    try:
        assert d.select_graph(copy).query("MATCH (m:Model) SET m.license = 'mit' RETURN count(m)").result_set[0][0] > 0
    finally:
        d.select_graph(copy).delete()
    assert d.select_graph("hub").ro_query("MATCH (m:Model) WHERE m.id = 'meta-llama/Llama-3.2-1B' RETURN m.id").result_set
    with pytest.raises(NoPermissionError):
        d.select_graph("hub").query(HUB_WRITE)
    with pytest.raises(NoPermissionError):
        d.connection.execute_command("GRAPH.COPY", "hub", "whatif:t-hubcopy")
    with pytest.raises(NoPermissionError):
        d.select_graph(f"org:{users['b']}").ro_query("MATCH (r) RETURN r")


def test_rulings_connect_as_the_org_user(monkeypatch):
    """With FINEPRINT_ORG_SECRET set, a new ruleset gets its own user on first write."""
    monkeypatch.setenv("FINEPRINT_ORG_SECRET", secrets.token_hex(16))
    graph.org_db.cache_clear()
    slug = "t-" + uuid.uuid4().hex[:8]
    try:
        r = rulings.create(slug, "license", "llama3.1", "approve", "commercial", "Approved.")
        assert [x["id"] for x in rulings.list_rulings(slug)] == [r["id"]]
        conn = graph.org_db(slug).connection
        assert conn.connection_pool.connection_kwargs["username"] == acl.org_user(slug)
        assert db().connection.execute_command("ACL", "GETUSER", acl.org_user(slug)) is not None
        with pytest.raises(NoPermissionError):
            graph.org_db(slug).select_graph("hub").query(HUB_WRITE)
    finally:
        rulings.drop(slug)
        db().connection.execute_command("ACL", "DELUSER", acl.org_user(slug))
        graph.org_db.cache_clear()
