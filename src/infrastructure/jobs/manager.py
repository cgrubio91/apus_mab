"""
Infrastructure: Job Manager (ThreadPool-based background jobs)

Los jobs viven en memoria durante su ejecución (el ThreadPool y el progreso
fino son por proceso), pero se espejan en la tabla MySQL `jobs` al crearse y
en cada cambio de estado, de modo que el historial y los resultados
sobreviven a un reinicio del servidor.
"""

import json
import threading
import logging
import time
import secrets
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable

from src.domain.entities.job import Job, JobStatus, JobCancelled

log = logging.getLogger("mapus.infrastructure.jobs")


class JobManager:

    def __init__(self, max_workers: int = 2, job_ttl: int = 7200):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job-worker")
        self._job_ttl = job_ttl
        self._restored = False

    # ── Persistencia en MySQL ────────────────────────────────────────
    def _persist(self, job: Job):
        """Espeja el job en la tabla `jobs`. Nunca lanza: la persistencia es
        best-effort y no debe romper la extracción."""
        try:
            from src.infrastructure.database.connection import execute_query
            execute_query(
                """INSERT INTO jobs (id, filename, status, progress, result, error, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       status = VALUES(status), progress = VALUES(progress),
                       result = VALUES(result), error = VALUES(error),
                       updated_at = VALUES(updated_at)""",
                (
                    job.id,
                    job.filename,
                    job.status.value,
                    json.dumps(job.progress, default=str),
                    json.dumps(job.result, default=str, ensure_ascii=False) if job.result is not None else None,
                    "; ".join(job.errors) if job.errors else None,
                    job.created_at,
                    job.updated_at,
                ),
                fetch=False,
            )
        except Exception:
            log.warning("No se pudo persistir el job %s (continúa en memoria)", job.id)

    def _restore_from_db(self):
        """Carga los jobs recientes de la BD al arrancar. Los que quedaron a
        medias en un proceso anterior se marcan como ERROR (su hilo murió)."""
        if self._restored:
            return
        self._restored = True
        try:
            from src.infrastructure.database.connection import execute_query
            cutoff = time.time() - self._job_ttl
            rows = execute_query(
                "SELECT * FROM jobs WHERE updated_at > %s ORDER BY created_at DESC LIMIT 100",
                (cutoff,),
            )
        except Exception:
            log.info("No se pudieron restaurar jobs desde la BD (¿tabla aún no creada?)")
            return

        for r in rows or []:
            if r["id"] in self._jobs:
                continue
            try:
                job = Job(id=r["id"], filename=r["filename"] or "")
                status = r["status"] or "ERROR"
                if status in (JobStatus.QUEUED, JobStatus.EXTRACTING, JobStatus.POST_PROCESSING):
                    # El proceso que lo ejecutaba ya no existe.
                    status = JobStatus.ERROR
                    job.errors = ["El servidor se reinició durante el procesamiento"]
                job.status = JobStatus(status)
                if r.get("progress"):
                    job.progress = json.loads(r["progress"]) if isinstance(r["progress"], str) else r["progress"]
                if r.get("result"):
                    job.result = json.loads(r["result"]) if isinstance(r["result"], str) else r["result"]
                if r.get("error") and not job.errors:
                    job.errors = [r["error"]]
                job.created_at = float(r["created_at"] or time.time())
                job.updated_at = float(r["updated_at"] or time.time())
                if job.status in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED):
                    job.completed_at = job.updated_at
                self._jobs[job.id] = job
            except Exception:
                log.warning("No se pudo restaurar el job %s", r.get("id"))
        if rows:
            log.info("Restaurados %d jobs desde la BD", len(self._jobs))

    def _get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def _cleanup_expired_jobs(self):
        now = time.time()
        expired = []
        for job_id, job in list(self._jobs.items()):
            if job.completed_at and now - job.completed_at > self._job_ttl:
                expired.append(job_id)
        for job_id in expired:
            del self._jobs[job_id]

    def create_job(self, filename: str) -> Job:
        job = Job(id=secrets.token_hex(8), filename=filename)
        with self._lock:
            self._cleanup_expired_jobs()
            self._jobs[job.id] = job
        self._persist(job)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            self._restore_from_db()
            self._cleanup_expired_jobs()
            return self._get_job(job_id)

    def list_jobs(self, limit: int = 20) -> list[Job]:
        with self._lock:
            self._restore_from_db()
            self._cleanup_expired_jobs()
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def update_progress(self, job_id: str, **kwargs):
        persist_job = None
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            if "status" in kwargs:
                job.status = JobStatus(kwargs["status"])
                persist_job = job
            if "result" in kwargs:
                job.result = kwargs["result"]
            if "errors" in kwargs:
                job.errors = kwargs["errors"]
            if "progress" in kwargs:
                job.progress.update(kwargs["progress"])
            if job.status in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED):
                job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1
        if persist_job:
            self._persist(persist_job)

    def update_phase(self, job_id: str, phase: str, **progress_kw):
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.progress["phase"] = phase
            job.progress.update(progress_kw)
            job.updated_at = time.time()
            job.progress_version += 1

    def set_result(self, job_id: str, result: dict):
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.result = result
            job.status = JobStatus.DONE
            job.progress.update({"pct": 100, "phase": "Completado"})
            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1
        self._persist(job)

    def set_error(self, job_id: str, error: str):
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.errors.append(error)
            job.status = JobStatus.ERROR
            job.progress.update({"phase": "Error"})
            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1
        self._persist(job)

    def submit(self, job_id: str, fn: Callable, *args, **kwargs):
        def progress_callback(pct: int, total_batches: int = 0, phase: Optional[str] = None, **extra_progress):
            with self._lock:
                job = self._get_job(job_id)
                if not job:
                    return
                if job.status == JobStatus.CANCELLED:
                    raise JobCancelled("El trabajo fue cancelado.")
                progress_data = {"pct": pct, "total_batches": total_batches, **extra_progress}
                if phase:
                    progress_data["phase"] = phase
                job.progress.update(progress_data)
                job.updated_at = time.time()
                job.progress_version += 1

        def _run():
            try:
                with self._lock:
                    job = self._get_job(job_id)
                    if job and job.status == JobStatus.CANCELLED:
                        return
                self.update_progress(job_id, status=JobStatus.EXTRACTING)
                kwargs["progress_callback"] = progress_callback
                result = fn(*args, **kwargs)
                self.update_progress(job_id, status=JobStatus.POST_PROCESSING)
                with self._lock:
                    job = self._get_job(job_id)
                    if job and job.status == JobStatus.CANCELLED:
                        return
                self.set_result(job_id, result)
            except JobCancelled:
                log.info("Job %s cancelado limpiamente.", job_id)
            except Exception:
                log.exception("Job %s falló durante ejecución.", job_id)
                self.set_error(job_id, "Error interno durante la ejecución")

        future = self._executor.submit(_run)
        with self._lock:
            job = self._get_job(job_id)
            if job:
                job.future = future
        return future

    def submit_job(self, job_id: str, fn: Callable, *args):
        def _run():
            try:
                fn(job_id, *args)
            except Exception:
                log.exception("Job %s falló en submit_job.", job_id)
                self.set_error(job_id, "Error interno durante la ejecución")

        future = self._executor.submit(_run)
        with self._lock:
            job = self._get_job(job_id)
            if job:
                job.future = future
        return future

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._get_job(job_id)
            if not job:
                return False
            cancelled = False
            if job.future:
                cancelled = job.future.cancel()
            if cancelled or job.status in (JobStatus.QUEUED, JobStatus.EXTRACTING, JobStatus.POST_PROCESSING):
                job.status = JobStatus.CANCELLED
                job.progress.update({"phase": "Cancelado"})
                job.completed_at = time.time()
                job.updated_at = time.time()
                job.progress_version += 1
                self._persist(job)
                return True
            return False

    def shutdown(self, wait: bool = True):
        self._executor.shutdown(wait=wait)


job_manager = JobManager()
