"""
Shared pytest setup.

Tenant-isolation note (P0.16)
-----------------------------
At runtime the app connects as the NON-superuser ``platform_app`` role, which
RLS governs, and carries the tenant via a request/background ContextVar. The
existing FUNCTIONAL test suite, however, seeds and reads RLS-protected tables
directly through ``get_engine()`` for many orgs without a request context — it
historically relied on the owner role bypassing RLS. To keep those tests
exercising business logic (not database plumbing), we point the cached app
engine at the OWNER (RLS-exempt) role for the test session.

The security property itself — that ``platform_app`` + RLS actually isolates
tenants — is proven separately and at full fidelity in
``tests/test_tenant_isolation_rls.py``, which builds an explicit ``platform_app``
engine rather than going through ``get_engine()``.

Follow-up (docs/dev/BACKLOG.md): migrate functional DB tests to run as the app
role under per-test ``org_context`` for end-to-end RLS coverage.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def _functional_tests_use_owner_engine():
    """Route get_engine() to the RLS-exempt owner role for functional tests.

    We patch the URL builder (not just the cached engine) so the routing
    survives tests that reset the cache via ``fact_store._engine = None``
    (e.g. test_ingestion_idempotency). test_tenant_isolation_rls imports
    ``app_engine_url`` from app.db.session directly, so it is unaffected and
    still exercises the real platform_app role."""
    import app.db.fact_store as fs
    from app.db.session import admin_engine_url

    orig = fs.app_engine_url
    fs.app_engine_url = admin_engine_url
    fs._engine = None
    yield
    fs.app_engine_url = orig
    fs._engine = None
