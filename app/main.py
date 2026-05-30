from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Info
from app.config import settings
from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.evaluation_routes import router as eval_router
from app.api.tenant_routes import router as tenant_router
from app.api.org_settings_routes import router as org_settings_router
from app.api.chat_routes import router as chat_router
from app.api.log_routes import router as log_router
from app.api.rfp_routes import router as rfp_router
from app.api.middleware import AuthMiddleware


def _run_migrations() -> None:
    """Apply any pending Alembic migrations on startup."""
    try:
        from alembic.config import Config
        from alembic import command
        import os
        cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        command.upgrade(cfg, "head")
        print("[startup] Alembic migrations: up to date")
    except Exception as exc:
        print(f"[startup] Alembic migration warning: {exc}")


def _check_cors_origins() -> None:
    """Refuse to start with wildcard CORS origins when an API key is set."""
    has_api_key = bool(settings.app_api_key and settings.app_api_key != "changeme-internal-api-key")
    has_wildcard = "*" in settings.allowed_origins
    if has_api_key and has_wildcard:
        raise RuntimeError(
            "CORS misconfiguration: ALLOWED_ORIGINS='*' is not permitted in production. "
            "Set ALLOWED_ORIGINS to your frontend domain(s) in .env, e.g.:\n"
            "  ALLOWED_ORIGINS=https://app.meridianai.com"
        )


def _is_production() -> bool:
    """A deployment is 'production' only when it has a real APP_API_KEY AND its
    CORS origins are not localhost-only. A localhost-only origin list means the
    app is being run for local development even if an APP_API_KEY happens to be
    set, so we must not block startup on dev-default secrets in that case. A real
    production deploy serves a real frontend domain, so the auth-secret guard
    still fires there.
    """
    has_api_key = bool(settings.app_api_key and settings.app_api_key != "changeme-internal-api-key")
    if not has_api_key:
        return False
    origins = settings.allowed_origins or []
    localhost_only = bool(origins) and all(
        "localhost" in o or "127.0.0.1" in o for o in origins
    )
    return not localhost_only


def _check_auth_secrets() -> None:
    """Refuse to start in production with default/unset auth secrets.

    In production a default JWT secret lets anyone forge a token for any
    org/role, and a default dev password is a known-credential admin login.
    """
    if not _is_production():
        return

    problems = []
    if not settings.jwt_secret_key or settings.jwt_secret_key == "change-me-in-production":
        problems.append(
            "JWT_SECRET_KEY is unset or still the default — anyone could forge tokens "
            "for any org_id/role. Set a strong random secret in .env."
        )
    if not settings.dev_user_password or settings.dev_user_password == "devpassword2026":
        problems.append(
            "DEV_USER_PASSWORD is unset or still the default — a known-credential "
            "admin login exists. Set DEV_USER_PASSWORD in .env (or disable the dev user)."
        )
    if settings.jwt_algorithm.lower() == "none":
        problems.append("JWT_ALGORITHM='none' disables signature verification.")

    if problems:
        raise RuntimeError(
            "AUTH MISCONFIGURATION — refusing to start in production:\n  - "
            + "\n  - ".join(problems)
        )


def _mark_orphaned_runs() -> None:
    """On startup, any run still 'running' was orphaned by a previous crash/restart."""
    try:
        import sqlalchemy as sa
        from app.db.fact_store import get_engine
        from app.infra.audit import audit
        engine = get_engine()
        with engine.begin() as conn:
            rows = conn.execute(
                sa.text("SELECT run_id::text, org_id::text FROM evaluation_runs WHERE status = 'running'")
            ).fetchall()
            if rows:
                conn.execute(
                    sa.text("UPDATE evaluation_runs SET status = 'interrupted' WHERE status = 'running'")
                )
                print(f"[startup] Marked {len(rows)} orphaned run(s) as interrupted")
        for run_id, org_id in rows:
            audit(org_id=org_id, run_id=run_id, event_type="run.interrupted",
                  actor="system", detail={"reason": "server_restart"})
    except Exception as exc:
        print(f"[startup] Could not mark orphaned runs: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_cors_origins()
    _check_auth_secrets()
    _run_migrations()
    _mark_orphaned_runs()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Agentic AI Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # AuthMiddleware must be added FIRST — before CORS
    app.add_middleware(AuthMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        allow_credentials=True,
    )

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(eval_router)
    app.include_router(tenant_router)
    app.include_router(org_settings_router)
    app.include_router(chat_router)
    app.include_router(log_router)
    app.include_router(rfp_router)

    Info("fastapi_app", "FastAPI application info").info({"app_name": "platform_api"})
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "1.0.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
