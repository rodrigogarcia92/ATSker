"""The production-database guard shared by the scripts that write to, or pay for, a database.

The production host is recognised by a fragment of its name, read from PROD_DB_HOST_FRAGMENT. The
real endpoint therefore never lives in tracked code. The guard fails closed: while the variable is
unset or empty, every non-local database is refused, because an unset variable must not switch the
protection off. Messages name the variable but never the host or the fragment.
"""

from urllib.parse import parse_qs, urlsplit

from src.config import get_settings

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def database_host(database_url: str) -> str:
    """The lower-case host a connection string reaches, or "" for SQLite and in-memory databases.

    libpq also reads `host` and `hostaddr` from the query string, and it uses them when the
    authority has no host, so they count here: a remote host hidden there must not look local.
    """
    parts = urlsplit(database_url)
    if parts.scheme.startswith("sqlite"):
        return ""
    query = parse_qs(parts.query)
    candidates = [parts.hostname or ""]
    candidates += [value for key in ("host", "hostaddr") for value in query.get(key, [])]
    return ",".join(candidate for candidate in candidates if candidate).lower()


def is_local(database_url: str) -> bool:
    """SQLite, in-memory, and no-host URLs (libpq falls back to a local socket), or loopback hosts.

    A host that starts with `/` is a Unix socket directory. Every entry must be local, so a
    comma-separated list with one remote host is not local.
    """
    entries = [entry for entry in database_host(database_url).split(",") if entry]
    if not entries:
        return True
    return all(entry.startswith("/") or entry in LOCAL_HOSTS for entry in entries)


def refusal_reason(
    database_url: str, *, allow_prod: bool, override: str | None = "--prod"
) -> str | None:
    """Why the script must not use this database, or None when it may.

    `allow_prod` is the explicit opt-in a script offers (`--prod`). `override` names that flag in
    the message, or is None when the script offers no override. An empty URL is not a database,
    so it is left to the caller's own check.
    """
    if not database_url.strip() or is_local(database_url):
        return None
    fragment = (get_settings().prod_db_host_fragment or "").strip().lower()
    if not fragment:
        return (
            "PROD_DB_HOST_FRAGMENT is not set, so this non-local database cannot be checked "
            "against the production host. Set it in .env (see .env.example), or point "
            "DATABASE_URL at a local database."
        )
    if fragment in database_host(database_url) and not allow_prod:
        hint = f"; pass {override} to confirm" if override else ""
        return f"refusing to use the production database{hint}"
    return None
