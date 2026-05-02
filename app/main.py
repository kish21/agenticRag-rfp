from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.middleware import AuthMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Agentic AI Platform",
        version="1.0.0",
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

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "skill": "01b-auth",
        }

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, reload=True)
