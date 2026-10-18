"""Database users, so tenant isolation is enforced by FalkorDB and not only by the API code.

- fp-hub-ro: GRAPH.RO_QUERY only, on `hub` and `family:*`. Reports read through it.
- fp-whatif: copies, edits and deletes `family:*` and `whatif:*`; on `hub` it may only run
  GRAPH.RO_QUERY (an ACL selector).
- fp-org-<slug>: GRAPH.QUERY / RO_QUERY / DELETE on its own `org:<slug>` key and nothing else.
- fp-admin: everything; the Clerk writes and per-org users are created through it.

FalkorDB declares the graph name as the command's key, so Redis key patterns apply to GRAPH.*
commands. Its key specs mark even GRAPH.RO_QUERY as read-write, so read-only access is enforced
by allowing only the RO_QUERY command, not with `%R~` patterns.

Passwords are random per boot. `python -m fineprint_core.acl` creates the users and prints
`export` lines for the shell that starts the API (deploy/start.sh).
"""
import hashlib
import hmac
import os
import secrets
import sys

HUB_RO = "fp-hub-ro"
WHATIF = "fp-whatif"
ADMIN = "fp-admin"
# The falkordb client runs INFO on connect; EXISTS is how graphs are checked without GRAPH.LIST.
BASE = ["+ping", "+info", "+exists"]


def org_user(slug: str) -> str:
    return f"fp-org-{slug}"


def org_password(slug: str, secret: str) -> str:
    return hmac.new(secret.encode(), slug.encode(), hashlib.sha256).hexdigest()


def rules_hub_ro() -> list[str]:
    return ["~hub", "~family:*", "+graph.ro_query", *BASE]


def rules_whatif() -> list[str]:
    return ["~family:*", "~whatif:*", "+graph.query", "+graph.ro_query", "+graph.copy", "+graph.delete",
            *BASE, "(~hub +graph.ro_query)"]


def rules_org(slug: str) -> list[str]:
    return [f"~org:{slug}", "+graph.query", "+graph.ro_query", "+graph.delete", *BASE]


def set_user(conn, name: str, password: str, rules: list[str]) -> None:
    conn.execute_command("ACL", "SETUSER", name, "reset", "on", f">{password}", *rules)


def ensure_org_user(conn, slug: str, secret: str) -> tuple[str, str]:
    name, pw = org_user(slug), org_password(slug, secret)
    set_user(conn, name, pw, rules_org(slug))
    return name, pw


def setup(conn, lock_default: bool = False) -> dict[str, str]:
    env = {
        "FINEPRINT_HUB_RO_PASSWORD": secrets.token_hex(24),
        "FINEPRINT_WHATIF_PASSWORD": secrets.token_hex(24),
        "FINEPRINT_ORG_SECRET": secrets.token_hex(24),
        "FALKORDB_USERNAME": ADMIN,
        "FALKORDB_PASSWORD": secrets.token_hex(24),
    }
    set_user(conn, HUB_RO, env["FINEPRINT_HUB_RO_PASSWORD"], rules_hub_ro())
    set_user(conn, WHATIF, env["FINEPRINT_WHATIF_PASSWORD"], rules_whatif())
    set_user(conn, ADMIN, env["FALKORDB_PASSWORD"], ["~*", "&*", "+@all"])
    if lock_default:
        conn.execute_command("ACL", "SETUSER", "default", "off")
    return env


if __name__ == "__main__":
    import redis
    r = redis.Redis(host=os.environ.get("FALKORDB_HOST", "127.0.0.1"), port=int(os.environ.get("FALKORDB_PORT", "6379")))
    out = setup(r, lock_default="--lock-default" in sys.argv)
    for k, v in out.items():
        print(f"export {k}={v}")
