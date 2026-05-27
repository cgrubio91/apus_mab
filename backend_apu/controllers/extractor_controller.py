import logging
import os
import tempfile
import json
import asyncio
import traceback

from fastapi import APIRouter, UploadFile, File, HTTPException, Body
from fastapi.responses import StreamingResponse

from ..services.job_manager import job_manager

log = logging.getLogger("mapus.backend.extractor")
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}


def _process_file(content: bytes, ext: str, filename: str, progress_callback=None):
    """The background task logic — runs in a thread."""
    log.info("_process_file START: %s (%d bytes, ext=%s)", filename, len(content), ext)
    
    from apu_extractor import (
        extract_apus_from_excel,
        extract_apus_from_pdf_batched,
        post_process_extracted_data,
        generate_copy_paste_table,
    )

    raw_insumos = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    log.info("_process_file: Temp file written to %s", tmp_path)

    try:
        if ext == ".pdf":
            log.info("_process_file: Starting PDF extraction...")
            raw_insumos = extract_apus_from_pdf_batched(tmp_path, filename, progress_callback=progress_callback)
            log.info("_process_file: PDF extraction returned %d raw insumos", len(raw_insumos))
        elif ext in (".xlsx", ".xls"):
            log.info("_process_file: Starting Excel extraction...")
            raw_insumos = extract_apus_from_excel(tmp_path, filename, progress_callback=progress_callback)
            log.info("_process_file: Excel extraction returned %d raw insumos", len(raw_insumos))

        if progress_callback:
            progress_callback(100, 100, "Limpiando y formateando datos...")

        cleaned = post_process_extracted_data(raw_insumos, filename)
        table = generate_copy_paste_table(cleaned)

        log.info("_process_file DONE: Extracted %d insumos from %s", len(cleaned), filename)

        return {
            "success": True,
            "filename": filename,
            "count": len(cleaned),
            "copy_paste_table": table,
            "insumos": cleaned,
        }
    except Exception as e:
        log.error("_process_file ERROR: %s\n%s", e, traceback.format_exc())
        raise
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
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
    
    # Create background job
    job = job_manager.create_job(filename)
    job_manager.submit(job.id, _process_file, content, ext, filename)

    return {"success": True, "job_id": job.id, "message": "Procesamiento iniciado en segundo plano"}


@router.get("/jobs")
async def get_jobs():
    jobs = job_manager.get_all_jobs()
    return {"jobs": [j.to_dict() for j in jobs]}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return job.to_dict()


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    log.info("SSE stream started for job %s (current status: %s)", job_id, job.status)

    async def event_stream():
        """
        Always send the current state every second, regardless of whether
        updated_at changed. This ensures the frontend always gets updates
        and avoids race conditions with thread timing.
        """
        tick = 0
        while True:
            try:
                data = job.to_json()
                yield f"data: {data}\n\n"
                tick += 1
                
                if tick % 10 == 0:
                    log.info("SSE tick %d for job %s: status=%s phase=%s pct=%d",
                             tick, job_id, job.status, job.progress.get("phase", "?"), job.progress.get("percent", 0))
            except Exception as e:
                log.error("SSE serialization error for job %s: %s", job_id, e)
                yield f"data: {json.dumps({'id': job_id, 'status': 'ERROR', 'error': str(e), 'progress': {'phase': 'Error de serialización', 'percent': 0, 'current_batch': 0, 'total_batches': 0}})}\n\n"
                break
            
            if job.status in ("DONE", "ERROR"):
                log.info("SSE stream ending for job %s (status: %s)", job_id, job.status)
                break
                
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/save-extracted")
async def save_extracted(payload: list = Body(...)):
    if not payload:
        raise HTTPException(status_code=400, detail="No hay datos para guardar.")

    import json
    from fastapi.responses import StreamingResponse
    from apu_extractor import insert_apus_stream

    total = len(payload)

    async def stream():
        for update in insert_apus_stream(payload):
            yield json.dumps(update) + "\n"

        log.info("Saved %d APU lines to database via streaming", total)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
