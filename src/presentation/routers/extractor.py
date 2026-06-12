"""
Presentation: File Extraction Routes
"""

import asyncio
import json
import logging
import os
import tempfile
import traceback
from typing import Any

import magic
from fastapi import APIRouter, Body, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from src.infrastructure.jobs.manager import job_manager
from src.application.use_cases.extract_apu import process_file
from src.application.use_cases.query_apus import save_extracted

log = logging.getLogger("mapus.presentation.extractor")
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_STREAM_SECONDS = 300

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado. Suba uno de: {', '.join(ALLOWED_EXTENSIONS)}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            total_bytes = 0
            is_first_chunk = True

            while chunk := await file.read(8192):
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024 ** 2)} MB).")

                if is_first_chunk:
                    detected_mime = magic.from_buffer(chunk[:4096], mime=True)
                    if detected_mime != ALLOWED_EXTENSIONS[ext]:
                        raise HTTPException(status_code=422, detail="El contenido real del archivo no coincide con su extensión.")
                    is_first_chunk = False

                tmp.write(chunk)

    except HTTPException:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Error al guardar archivo temporal: {e}")

    log.info("Archivo recibido y verificado: %s (%d bytes)", filename, total_bytes)

    job = job_manager.create_job(filename)
    job_manager.submit(job.id, process_file, tmp_path, ext, filename)

    return {"success": True, "job_id": job.id, "message": "Procesamiento iniciado en segundo plano"}


@router.post("/extract-file-async")
async def extract_file_async(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".pdf", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="Formato no soportado. Suba PDF (.pdf) o Excel (.xlsx, .xls).")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024*1024)} MB).")

    log.info("Async file upload: %s (%d bytes)", filename, len(content))

    from src.domain.entities.job import JobStatus
    from src.application.use_cases.extract_apu import run_extraction

    job = job_manager.create_job(filename)
    job_manager.update_progress(job.id, status=JobStatus.QUEUED)
    job_manager.submit_job(job.id, run_extraction, content, filename, ext, job_manager)

    return {"job_id": job.id, "status": "queued", "filename": filename}


@router.get("/jobs")
async def get_jobs() -> dict:
    jobs = job_manager.list_jobs(limit=1000)
    return {"jobs": [j.to_dict() for j in jobs]}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job.to_dict()


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    log.info("SSE stream abierto  job=%s  status=%s", job_id, job.status)

    async def event_stream():
        start = asyncio.get_event_loop().time()
        tick = 0

        while True:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > MAX_STREAM_SECONDS:
                log.warning("SSE timeout  job=%s  elapsed=%.0fs", job_id, elapsed)
                yield f"data: {json.dumps({'id': job_id, 'status': 'TIMEOUT'})}\n\n"
                break

            try:
                current_job = job_manager.get_job(job_id)
                if not current_job:
                    yield f"data: {json.dumps({'id': job_id, 'status': 'ERROR', 'error': 'El trabajo ya no existe'})}\n\n"
                    break

                yield f"data: {current_job.to_json()}\n\n"

                tick += 1
                if tick % 10 == 0:
                    log.debug("SSE tick=%d  job=%s  status=%s", tick, job_id, current_job.status)

                if current_job.status in ("DONE", "ERROR"):
                    log.info("SSE stream cerrado  job=%s  status=%s", job_id, current_job.status)
                    break

            except Exception as exc:
                log.error("SSE serialización  job=%s  error=%s", job_id, exc)
                yield f"data: {json.dumps({'id': job_id, 'status': 'ERROR', 'error': str(exc)})}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/save-extracted")
async def save_extracted_endpoint(payload: list[dict[str, Any]] = Body(...)):
    if not payload:
        raise HTTPException(status_code=400, detail="No hay datos para guardar.")

    async def stream():
        count = 0
        try:
            for update in save_extracted(payload):
                yield json.dumps(update) + "\n"
                count += 1
        except asyncio.CancelledError:
            log.warning("Cliente cerró la conexión en /save-extracted prematuramente.")
            raise
        finally:
            log.info("save_extracted: %d líneas procesadas", count)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
