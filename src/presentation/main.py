"""
Presentation: FastAPI Application Factory
Clean Architecture entry point — configures middleware, routers, and lifespan.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Ensure src is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.infrastructure.database.connection import execute_query
from src.infrastructure.database.schema import ensure_schema
from src.presentation.routers import api_router
from src.presentation.routers.whatsapp import router as whatsapp_router
from src.presentation.middleware import log_and_rate_limit

log = logging.getLogger("mapus")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
if CORS_ORIGINS == ["*"] and os.getenv("ENV", "").lower() == "production":
    # allow_origins="*" + allow_credentials=True es una combinación insegura:
    # cualquier sitio podría hacer peticiones autenticadas. En producción se exige
    # una lista explícita de orígenes.
    raise RuntimeError(
        "CORS_ORIGINS='*' no está permitido en producción. "
        "Define CORS_ORIGINS con los orígenes exactos del frontend."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_schema()
    except Exception as e:
        log.warning("Startup schema setup warning: %s", e)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="MAPUS API", version="2.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(log_and_rate_limit)

    # Dual prefix: /api/v1 (canonical) and /api (legacy)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api")
    app.include_router(whatsapp_router)

    @app.get("/")
    def home():
        return {
            "status": "online",
            "version": "2.1.0",
            "endpoints": {
                "extract_file": "POST /api/extract-file",
                "extract_file_async": "POST /api/extract-file-async",
                "save_extracted": "POST /api/save-extracted",
                "get_job": "GET /api/jobs/{job_id}",
                "stream_job": "GET /api/jobs/{job_id}/stream",
                "list_jobs": "GET /api/jobs",
                "projects": "GET /api/projects",
                "apus": "GET /api/apus",
                "chat_assistant": "POST /api/chat-assistant",
                "whatsapp_webhook": "POST /whatsapp_webhook",
            },
        }

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
