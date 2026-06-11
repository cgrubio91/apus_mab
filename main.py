"""
MAPUS Core Engine & API
=======================
WhatsApp bot (Twilio) + Angular REST frontend + Gemini AI extraction + PostgreSQL
"""

import asyncio
import json
import logging
import os
import re
import time
import base64
from datetime import datetime, date

from fastapi import FastAPI, Request, UploadFile, File, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg2.extras import RealDictCursor

from db_config import get_db_connection, execute_query
from apu_extractor import (
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
    insert_apus_batch,
    insert_apus_stream,
    get_unique_projects,
    get_apus,
    get_dashboard_stats,
    delete_project_apus,
)
from apu_extractor.ai_provider import generate_text as ai_generate
from apu_extractor.db_service import get_filter_options
from backend_apu.controllers.job_manager import JobStatus, job_manager
from backend_apu.controllers.analisis_apu_controller import router as analisis_apu_router

from twilio.rest import Client
from twilio.request_validator import RequestValidator

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mapus")

# ── Configuration ────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_APU_LIMIT = 500
CHAT_LIMIT = 30  # requests per window per IP
CHAT_WINDOW = 60  # seconds

# ── Twilio clients ───────────────────────────────────────────────────
twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None
twilio_validator = RequestValidator(AUTH_TOKEN) if AUTH_TOKEN else None

# ── FastAPI app ──────────────────────────────────────────────────────
app = FastAPI(title="MAPUS API", version="2.1.0")
app.include_router(analisis_apu_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Simple in-memory rate limiter ────────────────────────────────────
_rate_store: dict[str, list[float]] = {}


def _check_rate(key: str, max_req: int, window: float) -> bool:
    now = time.time()
    cutoff = now - window
    vals = _rate_store.get(key, [])
    vals = [t for t in vals if t > cutoff]
    if len(vals) >= max_req:
        return False
    vals.append(now)
    _rate_store[key] = vals
    return True


@app.middleware("http")
async def log_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"

    # Rate limit chat endpoint only
    if request.url.path == "/api/chat-assistant":
        if not _check_rate(f"chat:{ip}", CHAT_LIMIT, CHAT_WINDOW):
            return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes. Espera un momento."})

    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info("%s %s → %s (%.2fs)", request.method, request.url.path, response.status_code, elapsed)
    return response


# ── Gemini helpers ───────────────────────────────────────────────────
def gemini_generate(prompt: str) -> str:
    """Generate text using the configured AI provider (Gemini or Ollama)."""
    system = (
        "Eres un asistente experto en bases de datos PostgreSQL "
        "y en análisis de precios unitarios (APU) de obras civiles."
    )
    return ai_generate(prompt, system=system, timeout=300)


# ── SQL helpers ──────────────────────────────────────────────────────
_SQL_BLOCKED = re.compile(
    r"\b(drop\s|truncate\s|delete\s|insert\s|update\s|alter\s|"
    r"create\s|exec(ute)?\s|grant\s|revoke\s|copy\s|import\s)", re.IGNORECASE
)


def _validate_readonly_query(sql: str) -> bool:
    """Only allow SELECT queries; block any dangerous operations."""
    stripped = sql.strip()
    if not stripped.lower().startswith("select"):
        return False
    if _SQL_BLOCKED.search(stripped):
        return False
    return True


def ejecutar_sql(query: str):
    """Execute a SQL query (ideally parametrised) and return results as dicts."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception as e:
        log.error("SQL execution error: %s", e)
        return [{"error": str(e)}]
    finally:
        if conn:
            conn.close()


# ── WhatsApp helpers ────────────────────────────────────────────────
def send_whatsapp_message(to: str, text: str):
    """Send a WhatsApp message via Twilio."""
    if not twilio_client:
        log.warning("Twilio client not configured, skipping message to %s", to)
        return
    try:
        twilio_client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log.info("Message sent to %s (%d chars)", to, len(text))
    except Exception as e:
        log.error("Failed to send WhatsApp to %s: %s", to, e)


# ── User auth & conversational memory ────────────────────────────────
def usuario_autorizado(telefono: str):
    """Check if the user is authorised in the 'usuarios' table."""
    try:
        rows = execute_query(
            "SELECT * FROM usuarios WHERE telefono = %s AND activo = true",
            (telefono,),
        )
        return rows[0] if rows else None
    except Exception as e:
        log.error("Error checking user %s: %s", telefono, e)
        return None


def guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    """Save a conversation turn into the history table."""
    try:
        execute_query(
            """INSERT INTO historial_conversaciones
               (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
        log.info("Conversation stored for %s", telefono)
    except Exception as e:
        log.error("Failed to store conversation for %s: %s", telefono, e)


def obtener_historial(telefono: str, limite: int = 5):
    """Return the last N conversation records in chronological order."""
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s
               ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows))
    except Exception as e:
        log.error("Error retrieving history for %s: %s", telefono, e)
        return []


# ── Startup ──────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    """Create required tables on startup if they don't exist."""
    try:
        execute_query(
            """CREATE TABLE IF NOT EXISTS apus (
                id SERIAL PRIMARY KEY,
                fecha_aprobacion_apu DATE,
                fecha_analisis_apu DATE,
                ciudad VARCHAR(100),
                pais VARCHAR(100),
                entidad VARCHAR(200),
                contratista VARCHAR(200),
                nombre_proyecto VARCHAR(200),
                numero_contrato VARCHAR(100),
                item VARCHAR(50),
                items_descripcion TEXT,
                item_unidad VARCHAR(20),
                precio_unitario NUMERIC(30,10),
                precio_unitario_sin_aiu NUMERIC(30,10),
                codigo_insumo VARCHAR(50),
                tipo_insumo VARCHAR(100),
                insumo_descripcion TEXT,
                insumo_unidad VARCHAR(20),
                rendimiento_insumo NUMERIC(30,10),
                precio_unitario_apu NUMERIC(30,10),
                precio_parcial_apu NUMERIC(30,10),
                observacion TEXT,
                link_documento TEXT
            )""",
            fetch=False,
        )
        execute_query(
            """CREATE INDEX IF NOT EXISTS idx_apus_proyecto ON apus (nombre_proyecto)""",
            fetch=False,
        )
        execute_query(
            """CREATE INDEX IF NOT EXISTS idx_apus_ciudad ON apus (ciudad)""",
            fetch=False,
        )
        execute_query(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_apus_unique_conflict ON apus (numero_contrato, item, codigo_insumo, link_documento)""",
            fetch=False,
        )
        execute_query(
            """CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                telefono VARCHAR(50) NOT NULL UNIQUE,
                nombre VARCHAR(100),
                rol VARCHAR(20) DEFAULT 'user',
                activo BOOLEAN DEFAULT true,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            fetch=False,
        )
        execute_query(
            """CREATE TABLE IF NOT EXISTS historial_conversaciones (
                id SERIAL PRIMARY KEY,
                telefono VARCHAR(50) NOT NULL,
                mensaje_usuario TEXT NOT NULL,
                sql_generado TEXT,
                respuesta_bot TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            fetch=False,
        )
        execute_query(
            """CREATE INDEX IF NOT EXISTS idx_historial_telefono
               ON historial_conversaciones (telefono, timestamp DESC)""",
            fetch=False,
        )

        # ── Análisis APU tables ──────────────────────────────────────────
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
                item_unidad VARCHAR(20),
                precio_unitario NUMERIC(30,10),
                codigo_insumo TEXT,
                insumo_descripcion TEXT,
                insumo_unidad VARCHAR(20),
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


# ── Health ───────────────────────────────────────────────────────────
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


# ── File processing ──────────────────────────────────────────────────
@app.post("/api/extract-file")
async def extract_file(file: UploadFile = File(...), auto_save: bool = Query(True)):
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".pdf", ".xlsx", ".xls"):
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Suba PDF (.pdf) o Excel (.xlsx, .xls).",
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024*1024)} MB).",
        )

    log.info("File upload: %s (%d bytes)", filename, len(content))

    try:
        raw_insumos = []

        if ext == ".pdf":
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                raw_insumos = extract_apus_from_pdf_batched(tmp_path, filename)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        log.warning("Could not remove temp file (in use): %s", tmp_path)

        elif ext in (".xlsx", ".xls"):
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                raw_insumos = extract_apus_from_excel(tmp_path, filename)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        log.warning("Could not remove temp file (in use): %s", tmp_path)

        cleaned = post_process_extracted_data(raw_insumos, filename)
        table = generate_copy_paste_table(cleaned)

        log.info("Extracted %d insumos from %s", len(cleaned), filename)

        response = {
            "success": True,
            "filename": filename,
            "count": len(cleaned),
            "copy_paste_table": table,
            "insumos": cleaned,
        }

        if auto_save and cleaned:
            save_result = insert_apus_batch(cleaned)
            log.info("Auto-saved %d APU lines", save_result.get("count", 0))
            response["saved"] = save_result

        return response

    except HTTPException:
        raise
    except Exception as e:
        log.error("Error processing %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=f"Error procesando archivo: {e}")


@app.post("/api/save-extracted")
async def save_extracted(payload: list = Body(...)):
    if not payload:
        raise HTTPException(status_code=400, detail="No hay datos para guardar.")

    total = len(payload)

    async def stream():
        for update in insert_apus_stream(payload):
            yield json.dumps(update) + "\n"

        log.info("Saved %d APU lines to database", total)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ── Background Job Endpoints ─────────────────────────────────────────
import tempfile as _tempfile


def _run_extraction(job_id: str, content: bytes, filename: str, ext: str):
    from apu_extractor.gemini_extractor import (
        extract_apus_from_pdf_batched,
        extract_apus_from_excel,
        post_process_extracted_data,
        generate_copy_paste_table,
    )

    try:
        raw_insumos = []

        if ext == ".pdf":
            job_manager.update_phase(job_id, "Preparando PDF...")

            with _tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            def pdf_progress(batch_idx, total_batches, phase_text):
                job_manager.update_phase(
                    job_id,
                    phase_text,
                    current_batch=batch_idx,
                    total_batches=total_batches,
                    pct=round((batch_idx / total_batches) * 100) if total_batches > 0 else 0,
                )

            try:
                raw_insumos = extract_apus_from_pdf_batched(tmp_path, filename, progress_callback=pdf_progress)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        log.warning("Could not remove temp file: %s", tmp_path)

        elif ext in (".xlsx", ".xls"):
            job_manager.update_phase(job_id, "Preparando Excel...")

            with _tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            def excel_progress(batch_idx, total_batches, phase_text):
                job_manager.update_phase(
                    job_id,
                    phase_text,
                    current_batch=batch_idx,
                    total_batches=total_batches,
                    pct=round((batch_idx / total_batches) * 100) if total_batches > 0 else 0,
                )

            try:
                raw_insumos = extract_apus_from_excel(tmp_path, filename, progress_callback=excel_progress)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except PermissionError:
                        log.warning("Could not remove temp file: %s", tmp_path)

        job_manager.update_phase(job_id, "Post-procesando datos...", current_batch=0, total_batches=0, pct=95)
        time.sleep(0.5)

        cleaned = post_process_extracted_data(raw_insumos, filename)
        table = generate_copy_paste_table(cleaned)

        result = {
            "success": True,
            "filename": filename,
            "count": len(cleaned),
            "copy_paste_table": table,
            "insumos": cleaned,
        }

        job_manager.set_result(job_id, result)
        log.info("Job %s completed: %d insumos from %s", job_id, len(cleaned), filename)

    except Exception as e:
        log.error("Job %s failed: %s", job_id, e)
        job_manager.set_error(job_id, str(e))


@app.post("/api/extract-file-async")
async def extract_file_async(file: UploadFile = File(...)):
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".pdf", ".xlsx", ".xls"):
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Suba PDF (.pdf) o Excel (.xlsx, .xls).",
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024*1024)} MB).",
        )

    log.info("Async file upload: %s (%d bytes)", filename, len(content))

    job = job_manager.create_job(filename)
    job_manager.update_progress(job.id, status=JobStatus.QUEUED)

    job_manager.submit_job(job.id, _run_extraction, content, filename, ext)

    return {"job_id": job.id, "status": "queued", "filename": filename}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado.")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado.")

    async def event_stream():
        last_version = -1
        while True:
            current_job = job_manager.get_job(job_id)
            if not current_job:
                yield f"event: error\ndata: {json.dumps({'error': 'Job no encontrado'})}\n\n"
                break

            data = current_job.to_dict()

            if current_job.progress_version > last_version:
                last_version = current_job.progress_version
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"

            if current_job.status in (JobStatus.DONE, JobStatus.ERROR):
                event_type = "done" if current_job.status == JobStatus.DONE else "error"
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs")
async def list_jobs(limit: int = Query(20, ge=1, le=100)):
    jobs = job_manager.list_jobs(limit=limit)
    return {"jobs": [j.to_dict() for j in jobs]}


# ── DB queries ───────────────────────────────────────────────────────
@app.get("/api/projects")
async def get_projects():
    try:
        projects = get_unique_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/apus")
async def get_apus_endpoint(
    nombre_proyecto: str = Query(None),
    ciudad: str = Query(None),
    items_descripcion: str = Query(None),
    insumo_descripcion: str = Query(None),
    tipo_insumo: str = Query(None),
    contratista: str = Query(None),
    entidad: str = Query(None),
    codigo_insumo: str = Query(None),
    item: str = Query(None),
    item_unidad: str = Query(None),
    insumo_unidad: str = Query(None),
    pais: str = Query(None),
    numero_contrato: str = Query(None),
    search: str = Query(None),
    sort_by: str = Query(None),
    sort_order: str = Query("asc"),
    limit: int = Query(50, ge=1, le=MAX_APU_LIMIT),
    offset: int = Query(0, ge=0),
):
    filters = {k: v for k, v in locals().items()
               if v is not None and k not in ("limit", "offset", "search", "sort_by", "sort_order")}
    try:
        return get_apus(filters, limit, offset, sort_by=sort_by, sort_order=sort_order, search=search)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/apus/filter-options")
async def apus_filter_options():
    try:
        return get_filter_options()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/projects")
async def delete_project(nombre_proyecto: str = Query(..., min_length=1)):
    log.warning("Deleting project: %s", nombre_proyecto)
    try:
        return delete_project_apus(nombre_proyecto)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard")
async def dashboard():
    try:
        return get_dashboard_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Chat assistant (frontend) ────────────────────────────────────────
@app.post("/api/chat-assistant")
async def chat_assistant(payload: dict):
    message = (payload.get("message") or "").strip()
    telefono = (payload.get("telefono") or "web-user").strip()
    nombre = (payload.get("nombre") or "Usuario Web").strip()

    if not message:
        return {"reply": "Escribe una pregunta sobre tus APUs."}

    log.info("Chat query from %s: %s", telefono, message[:120])

    try:
        # 1. History context
        historial = obtener_historial(telefono, limite=5)
        ctx = ""
        if historial:
            ctx = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
            for i, c in enumerate(historial, 1):
                ctx += f"Usuario: {c['mensaje_usuario']}\n"
                if c.get("sql_generado"):
                    ctx += f"SQL generado: {c['sql_generado'][:100]}...\n"
            ctx += "\nUsa el contexto para entender referencias como 'el anterior', 'compara con...', etc.\n"

        # 2. Generate SQL
        prompt = f"""Actúa como un experto en PostgreSQL y APUs.

Tabla: apus
Columnas: fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad,
contratista, nombre_proyecto, numero_contrato, item, items_descripcion,
item_unidad, precio_unitario, precio_unitario_sin_aiu, codigo_insumo,
tipo_insumo, insumo_descripcion, insumo_unidad, rendimiento_insumo,
precio_unitario_apu, precio_parcial_apu, observacion, link_documento

REGLAS:
1. Siempre usa ILIKE con % para búsquedas parciales (nunca = para textos).
2. Mapea lenguaje natural: obra/nombre_proyecto, insumo/insumo_descripcion, precio/precio_unitario.
3. LIMIT 20 salvo que pida otra cantidad.
4. Solo SELECT. Sin explicaciones. Sin ```sql```.
{ctx}
Usuario: "{message}"
SQL:"""
        sql = gemini_generate(prompt)
        sql = re.sub(r"```sql|```", "", sql).strip()
        log.info("SQL generated: %s", sql[:200])

        results = []
        if not _validate_readonly_query(sql):
            reply = "Solo puedo realizar consultas de lectura."
        else:
            results = ejecutar_sql(sql)
            if not results or "error" in results[0]:
                reply = "No encontré registros en la base de datos."
            else:
                # Serialise datetimes & Decimals
                serialised = []
                for row in results:
                    r = {}
                    for k, v in row.items():
                        if isinstance(v, (datetime, date)):
                            r[k] = v.strftime("%Y-%m-%d")
                        elif hasattr(v, "__float__"):
                            r[k] = float(v) if v is not None else None
                        else:
                            r[k] = v
                    serialised.append(r)
                results = serialised

                prompt_summary = f"""Eres un ingeniero experto en APUs.
Resume los resultados de forma clara y profesional.
Saluda a {nombre}.
Resultados: {json.dumps(results[:15], ensure_ascii=False)}
Pregunta: "{message}"
"""
                reply = gemini_generate(prompt_summary)

        guardar_conversacion(telefono, message, sql if _validate_readonly_query(sql) else "", reply)
        return {"reply": reply, "sql_query": sql if _validate_readonly_query(sql) else None, "results": results}

    except Exception as e:
        log.error("Chat assistant error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── WhatsApp webhook ─────────────────────────────────────────────────
@app.post("/whatsapp_webhook")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
    except Exception as e:
        log.error("Failed to parse webhook form: %s", e)
        return "OK"

    from_number = (form.get("From") or "").strip()
    message_body = (form.get("Body") or "").strip()

    # ── Twilio signature verification ─────────────────────────────────
    if twilio_validator:
        signature = request.headers.get("X-Twilio-Signature", "")
        params = {k: v for k, v in form.items()}
        url = str(request.url).replace("http://", "https://")  # Twilio always signs HTTPS
        if not twilio_validator.validate(url, params, signature):
            log.warning("Invalid Twilio signature from %s", from_number)
            return "UNAUTHORIZED"

    log.info("WhatsApp from %s: %s", from_number, message_body[:120])

    # ── Auth ──────────────────────────────────────────────────────────
    user = usuario_autorizado(from_number)
    if not user:
        send_whatsapp_message(
            from_number,
            "Acceso restringido. No tienes permiso para usar este asistente.",
        )
        log.warning("Access denied to %s", from_number)
        return "UNAUTHORIZED"

    log.info("Authorised: %s (%s)", user["nombre"], user.get("rol", "?"))

    if not message_body:
        send_whatsapp_message(
            from_number,
            f"Hola {user['nombre']}! Envíame una pregunta sobre tus APUs.",
        )
        return "OK"

    # 1. History
    historial = obtener_historial(from_number, limite=5)
    ctx = ""
    if historial:
        ctx = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
        for i, c in enumerate(historial, 1):
            ctx += f"Usuario: {c['mensaje_usuario']}\n"
            if c.get("sql_generado"):
                ctx += f"SQL: {c['sql_generado'][:100]}...\n"
        ctx += "\nUsa el contexto para referencias.\n"

    # 2. SQL prompt
    prompt_sql = f"""Actúa como un experto en PostgreSQL y APUs.

Tabla: apus
Columnas: fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad,
contratista, nombre_proyecto, numero_contrato, item, items_descripcion,
item_unidad, precio_unitario, precio_unitario_sin_aiu, codigo_insumo,
tipo_insumo, insumo_descripcion, insumo_unidad, rendimiento_insumo,
precio_unitario_apu, precio_parcial_apu, observacion, link_documento

REGLAS:
1. Siempre ILIKE con % (nunca = para textos).
2. Mapea lenguaje natural a columnas.
3. LIMIT 20 salvo que pida otra cantidad.
4. Solo SELECT. Sin Markdown. Sin ```sql```.
{ctx}
Usuario: "{message_body}"
SQL:"""
    sql_query = gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
    log.info("WhatsApp SQL: %s", sql_query[:200])

    # 3. Execute
    if not _validate_readonly_query(sql_query):
        respuesta = "Solo se permiten consultas de lectura."
    else:
        resultados = ejecutar_sql(sql_query)
        if not resultados or "error" in resultados[0]:
            respuesta = "No se encontraron resultados."
        else:
            prompt_resumen = f"""Eres un ingeniero experto en APUs.
Presenta los resultados para WhatsApp de forma clara y profesional.

FORMATO:
- LISTADOS: 1., 2., 3., con datos relevantes
- COMPARACIONES: tabla con |
- AGREGACIONES: destaca el resultado
- Sin Markdown, usa MAYÚSCULAS para títulos
- Máximo 60 caracteres por línea
- Máximo 15 resultados

Usuario: {user['nombre']}
Pregunta: "{message_body}"
Resultados: {json.dumps(resultados, ensure_ascii=False, default=str)}
"""
            respuesta = gemini_generate(prompt_resumen)

    guardar_conversacion(from_number, message_body, sql_query if _validate_readonly_query(sql_query) else "", respuesta)

    # 4. Chunk & send
    if len(respuesta) > 1500:
        partes = [respuesta[i:i+1500] for i in range(0, len(respuesta), 1500)]
        for i, parte in enumerate(partes):
            send_whatsapp_message(from_number, parte)
            log.info("Chunk %d/%d sent (%d chars)", i + 1, len(partes), len(parte))
            time.sleep(2)
    else:
        send_whatsapp_message(from_number, respuesta)

    return "OK"


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10000))
    log.info("Starting MAPUS server on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)



