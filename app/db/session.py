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
remember to ``SET`` it. It is RESET on ``checkin`` so a pooled connection never
leaks one tenant's context into another tenant's request.

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

    Uses set_config(...) — parameterised, injection-safe — at SESSION scope so
    it survives across the multiple transactions a single checked-out
    connection may run. Cleared (empty string) when no tenant is active, which
    makes every RLS policy (``org_id::text = current_setting(...)``) match zero
    rows rather than fall open.
    """
    cur = dbapi_conn.cursor()
    try:
        cur.execute(
            "SELECT set_config('app.current_org_id', %s, false)",
            (org_id or "",),
        )
    finally:
        cur.close()


def install_org_listener(engine: sa.Engine) -> None:
    """Attach pool listeners that bind app.current_org_id to the ContextVar.

    checkout → stamp the active org onto the connection before the caller uses
    it. checkin → reset to empty so the connection carries no tenant context
    back into the pool (prevents cross-request leakage)."""

    @sa.event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_conn, conn_record, conn_proxy):  # noqa: ANN001
        _apply_org_context(dbapi_conn, _current_org_id.get())

    @sa.event.listens_for(engine, "checkin")
    def _on_checkin(dbapi_conn, conn_record):  # noqa: ANN001
        try:
            _apply_org_context(dbapi_conn, None)
        except Exception:
            # A dead/closed connection on checkin must not raise; the pool
            # will discard it. Context is re-stamped on the next checkout.
            pass


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
