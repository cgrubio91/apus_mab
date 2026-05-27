import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db_config import execute_query
from .api import api_router

log = logging.getLogger("mapus.backend")


def create_app() -> FastAPI:
    app = FastAPI(
        title="MAPUS API - APU Module",
        description="Procesador de APUs - Módulo Backend",
        version="2.1.0",
    )

    origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
