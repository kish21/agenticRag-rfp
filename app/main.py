from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.evaluation_routes import router as eval_router
from app.api.tenant_routes import router as tenant_router
from app.api.middleware import AuthMiddleware


def _mark_orphaned_runs() -> None:
    """On startup, any run still 'running' was orphaned by a previous crash/restart."""
    try:
        import sqlalchemy as sa
        from app.db.fact_store import get_engine
        from app.core.audit import audit
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
        allow_origins=["*"] if settings.app_api_key else ["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(eval_router)
    app.include_router(tenant_router)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "skill": "01b-auth",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
