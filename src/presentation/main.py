"""
Presentation: FastAPI Application Factory
Clean Architecture entry point — configures middleware, routers, and lifespan.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# El HTML de la SPA no debe cachearse: si el navegador retiene un index.html viejo
# tras un redeploy, sigue pidiendo bundles con hash que ya no existen en disco.
_INDEX_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

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

    # Movemos la info de la API a una ruta alternativa por si quieres consultarla
    @app.get("/api/status")
    def api_status():
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

    # ── Soporte para Servir Angular (Frontend) ────────────────────────
    STATIC_DIR = "/app/static"

    if os.path.exists(STATIC_DIR):
        # 1. Buscamos el index.html en la carpeta static
        # (Angular compila dentro de dist/ o dist/nombre-app/, el Dockerfile se encarga de unificar esto en /app/static)
        index_path = os.path.join(STATIC_DIR, "index.html")

        # Si Angular compiló en una subcarpeta (ej. /app/static/browser/index.html) ajustamos dinámicamente:
        if not os.path.exists(index_path):
            for root, dirs, files in os.walk(STATIC_DIR):
                if "index.html" in files:
                    STATIC_DIR = root
                    index_path = os.path.join(root, "index.html")
                    break

        log.info("Serving Angular frontend from: %s", STATIC_DIR)
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        # 2. Servimos la raíz del sitio con Angular
        @app.get("/")
        async def serve_home():
            return FileResponse(index_path, headers=_INDEX_NO_CACHE_HEADERS)

        # 3. Wildcard para no romper el ruteo interno de Angular
        @app.get("/{catchall:path}")
        async def serve_frontend(catchall: str):
            # No interferimos con las peticiones de la API ni de WhatsApp
            if not catchall.startswith("api") and not catchall.startswith("whatsapp"):
                file_path = os.path.join(STATIC_DIR, catchall)
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    return FileResponse(file_path)
                # Un asset con extensión (bundle .js/.css con hash) que no existe es un
                # 404 real, no una ruta de Angular: si se sirve index.html en su lugar,
                # el navegador lo recibe con Content-Type equivocado y lo descarta en
                # silencio, dejando la app sin estilos tras un redeploy.
                if os.path.splitext(catchall)[1]:
                    raise HTTPException(status_code=404)
                return FileResponse(index_path, headers=_INDEX_NO_CACHE_HEADERS)
    else:
        # Fallback por si la carpeta no existe en desarrollo local
        @app.get("/")
        def home():
            return {"status": "online", "message": "Static folder not found. API is ready."}

    return app


app = create_app()