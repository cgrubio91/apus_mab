"""
Application: Extract APU Use Case
File processing orchestration — receives temp file path, delegates to AI, returns results.
"""

import logging
import os
import traceback

from src.infrastructure.ai.gemini_extractor import (
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
)

log = logging.getLogger("mapus.application.extract")


def process_file(tmp_path: str, ext: str, filename: str, progress_callback=None) -> dict:
    log.info("process_file START  file=%s  path=%s  ext=%s", filename, tmp_path, ext)
    raw_insumos = []

    try:
        if ext == ".pdf":
            raw_insumos = extract_apus_from_pdf_batched(tmp_path, filename, progress_callback=progress_callback)
        elif ext in (".xlsx", ".xls"):
            raw_insumos = extract_apus_from_excel(tmp_path, filename, progress_callback=progress_callback)

        log.info("process_file: %d insumos raw extraídos", len(raw_insumos))

        if progress_callback:
            progress_callback(100, 100, "Limpiando y formateando datos…")

        cleaned = post_process_extracted_data(raw_insumos, filename)
        table = generate_copy_paste_table(cleaned)

        log.info("process_file DONE  insumos=%d  file=%s", len(cleaned), filename)
        return {
            "success": True,
            "filename": filename,
            "count": len(cleaned),
            "copy_paste_table": table,
            "insumos": cleaned,
        }

    except Exception:
        log.error("process_file ERROR  file=%s\n%s", filename, traceback.format_exc())
        raise

    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                log.info("process_file: temp file deleted → %s", tmp_path)
        except OSError as e:
            log.error("Could not delete temp file %s: %s", tmp_path, e)


def run_extraction(job_id: str, content: bytes, filename: str, ext: str, job_manager):
    """Background extraction worker that updates job state."""
    import tempfile as _tempfile
    import time

    from src.infrastructure.ai.gemini_extractor import (
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
                    job_id, phase_text,
                    current_batch=batch_idx, total_batches=total_batches,
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
                    job_id, phase_text,
                    current_batch=batch_idx, total_batches=total_batches,
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

        result = {"success": True, "filename": filename, "count": len(cleaned), "copy_paste_table": table, "insumos": cleaned}

        job_manager.set_result(job_id, result)
        log.info("Job %s completed: %d insumos from %s", job_id, len(cleaned), filename)

    except Exception as e:
        log.error("Job %s failed: %s", job_id, e)
        job_manager.set_error(job_id, str(e))
