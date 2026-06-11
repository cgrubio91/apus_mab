import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
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

    @app.on_event("startup")
    def startup():
        try:
            execute_query(
                """CREATE TABLE IF NOT EXISTS solicitudes_apu (
                    id SERIAL PRIMARY KEY,
                    link_documento TEXT,
                    contratista VARCHAR(200),
                    nombre_proyecto VARCHAR(200),
                    fecha_solicitud DATE DEFAULT CURRENT_DATE,
                    fecha_limite_respuesta DATE,
                    fecha_limite_aprobacion DATE,
                    estado VARCHAR(50) DEFAULT 'pendiente_analisis',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                fetch=False,
            )
            execute_query(
                """CREATE TABLE IF NOT EXISTS solicitud_insumos (
                    id SERIAL PRIMARY KEY,
                    solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE,
                    grupo_cotizacion INTEGER DEFAULT 1,
                    nombre_archivo TEXT,
                    item TEXT,
                    items_descripcion TEXT,
                    item_unidad TEXT,
                    precio_unitario NUMERIC(30,10),
                    codigo_insumo TEXT,
                    insumo_descripcion TEXT,
                    insumo_unidad TEXT,
                    rendimiento_insumo NUMERIC(30,10),
                    tipo_insumo VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                fetch=False,
            )
            execute_query(
                """CREATE TABLE IF NOT EXISTS analisis_apu (
                    id SERIAL PRIMARY KEY,
                    solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE UNIQUE,
                    analisis_json JSONB,
                    resumen TEXT,
                    recomendacion VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                fetch=False,
            )
            execute_query(
                """CREATE TABLE IF NOT EXISTS historial_aprobaciones (
                    id SERIAL PRIMARY KEY,
                    solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE,
                    accion VARCHAR(50),
                    responsable_rol VARCHAR(100),
                    responsable_nombre VARCHAR(200),
                    motivo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                fetch=False,
            )
            execute_query(
                """CREATE TABLE IF NOT EXISTS aprendizaje_rechazos (
                    id SERIAL PRIMARY KEY,
                    analisis_id INTEGER REFERENCES analisis_apu(id),
                    motivo_rechazo TEXT,
                    contexto TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                fetch=False,
            )
            try:
                execute_query(
                    """ALTER TABLE solicitud_insumos ADD COLUMN IF NOT EXISTS grupo_cotizacion INTEGER DEFAULT 1""",
                    fetch=False,
                )
                execute_query(
                    """ALTER TABLE solicitud_insumos ADD COLUMN IF NOT EXISTS nombre_archivo TEXT""",
                    fetch=False,
                )
                execute_query(
                    """ALTER TABLE solicitud_insumos ALTER COLUMN item TYPE TEXT""",
                    fetch=False,
                )
                execute_query(
                    """ALTER TABLE solicitud_insumos ALTER COLUMN codigo_insumo TYPE TEXT""",
                    fetch=False,
                )
            except Exception:
                pass
            log.info("Database schema verified — all tables active")
        except Exception as e:
            log.warning("Startup schema setup warning: %s", e)

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
