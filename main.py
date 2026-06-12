"""
MAPUS Core Engine & API
=======================
WhatsApp bot (Twilio) + Angular REST frontend + Gemini AI extraction + PostgreSQL
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db_config import get_db_connection, execute_query
from db_schema import ensure_schema
from apu_extractor import (
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
    insert_apus_batch,
)
from backend_apu.controllers.job_manager import JobStatus, job_manager

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
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
if CORS_ORIGINS == ["*"] and os.getenv("ENV", "").lower() == "production":
    log.warning("CORS configurado como '*' en producción. Esto NO es seguro.")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_schema()
    except Exception as e:
        log.warning("Startup schema setup warning: %s", e)
    yield


app = FastAPI(title="MAPUS API", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Import backend_apu controllers ───────────────────────────────────
from backend_apu.api import api_router
from backend_apu.controllers.whatsapp_controller import router as whatsapp_router

# Dual prefix: /api/v1 (canonical) and /api (legacy) for backwards compatibility
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")
app.include_router(whatsapp_router)

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
    if request.url.path == "/api/chat-assistant":
        if not _check_rate(f"chat:{ip}", 30, 60):
            return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes. Espera un momento."})
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info("%s %s → %s (%.2fs)", request.method, request.url.path, response.status_code, elapsed)
    return response


# ── Home & Health ────────────────────────────────────────────────────
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


# ── Background extraction worker ─────────────────────────────────────
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


# ── Async extraction endpoint (unique, not in backend_apu) ──────────
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


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10000))
    log.info("Starting MAPUS server on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
