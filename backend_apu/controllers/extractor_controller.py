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
from pydantic import BaseModel, Field

from ..services.job_manager import job_manager
from apu_extractor import (
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    insert_apus_stream,
    post_process_extracted_data,
    generate_copy_paste_table,
)

log = logging.getLogger("mapus.backend.extractor")
router = APIRouter()

# ---------------------------------------------------------------------------
# Constantes (mueve a settings.py / pydantic-settings cuando puedas)
# ---------------------------------------------------------------------------
MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB
MAX_STREAM_SECONDS: int = 300          # 5 min SSE timeout

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class InsumoItem(BaseModel):
    """Representa un insumo/APU extraído. Ajusta los campos a tu modelo real."""
    codigo:      str | None   = Field(None, description="Código del insumo")
    descripcion: str          = Field(...,  description="Descripción del insumo")
    unidad:      str | None   = Field(None, description="Unidad de medida")
    cantidad:    float | None = Field(None, ge=0)
    precio:      float | None = Field(None, ge=0)
    extra:       dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Lógica de extracción (se ejecuta en un thread del ThreadPoolExecutor)
# ---------------------------------------------------------------------------
def _process_file(
    tmp_path: str,
    ext: str,
    filename: str,
    progress_callback=None,
) -> dict[str, Any]:
    """
    Recibe la RUTA del temporal en lugar de los bytes para no saturar la RAM.
    El thread es responsable de eliminar el archivo al terminar.
    """
    log.info("_process_file START  file=%s  path=%s  ext=%s", filename, tmp_path, ext)
    raw_insumos: list = []

    try:
        if ext == ".pdf":
            log.info("_process_file: iniciando extracción PDF…")
            raw_insumos = extract_apus_from_pdf_batched(
                tmp_path, filename, progress_callback=progress_callback
            )
        elif ext in (".xlsx", ".xls"):
            log.info("_process_file: iniciando extracción Excel…")
            raw_insumos = extract_apus_from_excel(
                tmp_path, filename, progress_callback=progress_callback
            )

        log.info("_process_file: %d insumos raw extraídos", len(raw_insumos))

        if progress_callback:
            progress_callback(100, 100, "Limpiando y formateando datos…")

        cleaned = post_process_extracted_data(raw_insumos, filename)
        table   = generate_copy_paste_table(cleaned)

        log.info("_process_file DONE  insumos=%d  file=%s", len(cleaned), filename)
        return {
            "success":          True,
            "filename":         filename,
            "count":            len(cleaned),
            "copy_paste_table": table,
            "insumos":          cleaned,
        }

    except Exception:
        log.error("_process_file ERROR  file=%s\n%s", filename, traceback.format_exc())
        raise

    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                log.info("_process_file: temporal eliminado → %s", tmp_path)
        except OSError as e:
            log.error("No se pudo eliminar el temporal %s: %s", tmp_path, e)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    filename = file.filename or "unknown"
    ext      = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Suba uno de: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # tmp_path = None antes del try para evitar usar locals() en el except
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path     = tmp.name
            total_bytes  = 0
            is_first_chunk = True

            # Lectura en chunks de 8 KB: valida tamaño y magic bytes al vuelo
            while chunk := await file.read(8192):
                total_bytes += len(chunk)

                if total_bytes > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024 ** 2)} MB).",
                    )

                if is_first_chunk:
                    detected_mime = magic.from_buffer(chunk[:4096], mime=True)
                    if detected_mime != ALLOWED_EXTENSIONS[ext]:
                        raise HTTPException(
                            status_code=422,
                            detail="El contenido real del archivo no coincide con su extensión.",
                        )
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

    log.info(
        "Archivo recibido y verificado: %s (%d bytes en disco → %s)",
        filename, total_bytes, tmp_path,
    )

    job = job_manager.create_job(filename)
    job_manager.submit(job.id, _process_file, tmp_path, ext, filename)

    return {
        "success": True,
        "job_id":  job.id,
        "message": "Procesamiento iniciado en segundo plano",
    }


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

    log.info("SSE stream abierto  job=%s  status=%s", job_id, job.status)

    async def event_stream():
        start = asyncio.get_event_loop().time()
        tick  = 0

        while True:
            # ── Timeout ───────────────────────────────────────────────────
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > MAX_STREAM_SECONDS:
                log.warning("SSE timeout  job=%s  elapsed=%.0fs", job_id, elapsed)
                yield f"data: {json.dumps({'id': job_id, 'status': 'TIMEOUT'})}\n\n"
                break

            # ── Obtener estado y emitir ───────────────────────────────────
            try:
                current_job = job_manager.get_job(job_id)
                if not current_job:
                    yield f"data: {json.dumps({'id': job_id, 'status': 'ERROR', 'error': 'El trabajo ya no existe'})}\n\n"
                    break

                yield f"data: {current_job.to_json()}\n\n"

                # tick y log dentro del try para que current_job siempre esté definida
                tick += 1
                if tick % 10 == 0:
                    log.debug(
                        "SSE tick=%d  job=%s  status=%s",
                        tick, job_id, current_job.status,
                    )

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
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/save-extracted")
async def save_extracted(payload: list[InsumoItem] = Body(...)):
    if not payload:
        raise HTTPException(status_code=400, detail="No hay datos para guardar.")

    raw_payload = [item.model_dump() for item in payload]

    async def stream():
        count = 0
        try:
            for update in insert_apus_stream(raw_payload):
                yield json.dumps(update) + "\n"
                count += 1
        except asyncio.CancelledError:
            log.warning("Cliente cerró la conexión en /save-extracted prematuramente.")
            raise
        finally:
            log.info("save_extracted: %d líneas procesadas", count)

    return StreamingResponse(stream(), media_type="application/x-ndjson")