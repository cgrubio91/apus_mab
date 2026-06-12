import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from db_config import execute_query
from db_schema import ensure_schema
from .api import api_router

log = logging.getLogger("mapus.backend")


def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            ensure_schema()
        except Exception as e:
            log.warning("Startup schema setup warning: %s", e)
        yield

    app = FastAPI(
        title="MAPUS API - APU Module",
        description="Procesador de APUs - Módulo Backend",
        version="2.1.0",
        lifespan=lifespan,
    )

    origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dual prefix: /api/v1 (canonical) and /api (legacy) for backwards compatibility
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api")

    @app.get("/")
    def root():
        return {"status": "online", "module": "apus"}

    @app.get("/health")
    def health():
        status = {"status": "ok", "database": "connected"}
        try:
            execute_query("SELECT 1")
        except Exception as e:
            status["status"] = "error"
            status["database"] = str(e)
            log.error("Health check failed: %s", e)
        return status

    return app


app = create_app()
