"""
Tenant-isolation session machinery (P0.16).

Two engines, two trust levels:

  • app engine  (postgres_app_user / ``platform_app``) — a NON-superuser,
    NON-owner role. PostgreSQL Row-Level Security only constrains a role that
    is neither the table owner nor a superuser/BYPASSRLS role, so EVERY
    request-scoped and per-org background query goes through this engine. If a
    query forgets its ``WHERE org_id`` filter, RLS is the backstop that still
    returns zero cross-tenant rows.

  • admin engine (postgres_user / ``platformuser``) — the owner/superuser role.
    RLS does not apply to it. Used ONLY for things that legitimately span orgs
    or run before an org context exists: DDL/migrations, the startup
    orphaned-run sweep, the identity/auth lookups (login resolves which org an
    email belongs to), and cross-org cron jobs.

The org context (``app.current_org_id``, read by every RLS policy) is carried
in a ContextVar and stamped onto each app-engine connection by a pool
``checkout`` listener — so route handlers and DB helpers do NOT each have to
remember to ``SET`` it. The stamp is COMMITTED at checkout, so a later
transaction rollback on that pooled connection cannot silently undo it; and it
is re-applied (overwritten) whenever the active tenant differs, so a pooled
connection can never serve another tenant with a stale context.

Request scope: AuthMiddleware sets the ContextVar from the verified JWT.
Background scope: wrap per-org work in ``with org_context(org_id): ...``.
"""
from __future__ import annotations

import contextlib
import contextvars

import sqlalchemy as sa

from app.config import settings

# The org_id whose rows the current logical task is allowed to touch.
# None  → no tenant context (RLS sees empty string → zero protected rows).
_current_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_org_id", default=None
)


def set_current_org(org_id: str | None) -> None:
    """Set the active tenant for the current context (e.g. from a request's JWT)."""
    _current_org_id.set(str(org_id) if org_id else None)


def get_current_org() -> str | None:
    return _current_org_id.get()


@contextlib.contextmanager
def org_context(org_id: str | None):
    """Scope a block of work to one tenant. Use in background tasks / jobs that
    have no request to carry the ContextVar. Restores the prior value on exit."""
    token = _current_org_id.set(str(org_id) if org_id else None)
    try:
        yield
    finally:
        _current_org_id.reset(token)


def _apply_org_context(dbapi_conn, org_id: str | None) -> None:
    """Stamp (or clear) app.current_org_id on a raw DBAPI connection.

    Uses set_config(..., is_local=false) — parameterised, injection-safe — at
    SESSION scope so it survives across the multiple transactions a single
    checked-out connection may run, then COMMITS it immediately.

    Why the commit matters: a session-level ``SET`` issued inside a transaction
    is rolled back with that transaction. Without the commit, a stamp applied at
    checkout would silently vanish the moment the caller's request hit an error
    and rolled back — yet the cached ``app_org`` marker would still report the
    connection as stamped, so the NEXT borrower ran with an empty tenant and RLS
    hid every row (the "run not found" / empty-list bug). Committing pins the
    GUC for the whole session, immune to any later rollback, keeping the GUC and
    the cache marker in lock-step. Safe to commit here: the pool hands the
    connection out clean (reset-on-return), so no caller transaction is open yet.

    Cleared (empty string) when no tenant is active, which makes every RLS policy
    (``org_id::text = current_setting(...)``) match zero rows rather than fall open.
    """
    cur = dbapi_conn.cursor()
    try:
        cur.execute(
            "SELECT set_config('app.current_org_id', %s, false)",
            (org_id or "",),
        )
    finally:
        cur.close()
    # Persist the session GUC so a later transaction rollback on this pooled
    # connection cannot undo it (see docstring).
    dbapi_conn.commit()


def install_org_listener(engine: sa.Engine) -> None:
    """Attach a pool checkout listener that binds app.current_org_id to the
    ContextVar.

    On every checkout the active org is stamped onto the connection *before*
    the caller uses it — so the connection always carries the correct tenant at
    the point of query, and a connection returned to the pool can never serve
    another tenant with a stale context (the next checkout overwrites it).

    Perf: we remember the last value set on each physical connection
    (``conn_record.info``) and only issue the ``set_config`` round-trip when the
    org actually changes. A single-tenant request running many queries on the
    same pooled connection therefore pays at most one extra round-trip, not one
    per query — RLS adds negligible overhead to an evaluation run."""

    @sa.event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, conn_record):  # noqa: ANN001
        # New physical connection carries no session GUC — drop any cached marker
        # so the next checkout re-applies it (handles pool recycle/invalidate).
        conn_record.info.pop("app_org", None)

    @sa.event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_conn, conn_record, conn_proxy):  # noqa: ANN001
        org = _current_org_id.get() or ""
        if conn_record.info.get("app_org") != org:
            _apply_org_context(dbapi_conn, org)
            conn_record.info["app_org"] = org


def _url(user: str, password: str) -> str:
    return (
        f"postgresql://{user}:{password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def app_engine_url() -> str:
    """DB URL for the RLS-governed application role."""
    # Fall back to the owner password only if the app password is unset, so a
    # half-configured .env still boots in dev (the owner role is created with
    # the same password in docker-compose/dev). Production sets both.
    pw = settings.postgres_app_password or settings.postgres_password
    return _url(settings.postgres_app_user, pw)


def admin_engine_url() -> str:
    """DB URL for the owner/superuser role (RLS-exempt; DDL + system paths)."""
    return _url(settings.postgres_user, settings.postgres_password)
