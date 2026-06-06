"""DX-001 (#128) — response-body snapshot regression.

Criterion #3: the annotation-only change must not alter any response body. The
strongest structural guarantee is in test_openapi_annotations.py
(test_response_model_set_is_unchanged) — no NEW response_model was added, so no
route's body can be silently filtered. This file adds a live body snapshot for
the routes reachable without a database:

  • /health — a raw-dict 200, the simplest "body unchanged" check.
  • /metrics — still served, but now excluded from the OpenAPI schema.
  • an authenticated route with no token — returns 401 before any handler/DB,
    confirming the {'detail': ...} envelope the docs now promise.

TestClient is used WITHOUT its lifespan context manager, so startup
(migrations / DB role checks) does not run and no database is required.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_body_unchanged():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "version": "1.0.0"}


def test_metrics_served_but_excluded_from_schema():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "/metrics" not in app.openapi()["paths"]


def test_authenticated_route_401_envelope_matches_docs():
    r = client.get("/api/v1/evaluate/list")
    assert r.status_code == 401
    body = r.json()
    assert list(body.keys()) == ["detail"]
