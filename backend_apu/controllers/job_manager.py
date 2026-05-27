import json
import time
import threading
import logging
import secrets

from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable

log = logging.getLogger("mapus.jobs")


# ======================================================
# EXCEPTIONS
# ======================================================

class JobCancelled(Exception):
    """Excepción controlada para detener jobs cancelados."""
    pass


# ======================================================
# ENUMS
# ======================================================

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    POST_PROCESSING = "POST_PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


# ======================================================
# MODEL
# ======================================================

@dataclass
class Job:
    id: str
    filename: str

    status: JobStatus = JobStatus.QUEUED

    progress: dict = field(default_factory=lambda: {
        "phase": "En cola...",
        "current_batch": 0,
        "total_batches": 0,
        "current_page": 0,
        "total_pages": 0,
        "pct": 0,
    })

    result: Optional[dict] = None
    errors: list[str] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    progress_version: int = 0

    # Evita serialización accidental del Future
    future: Optional[Future] = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status.value,

            # Defensive copy
            "progress": dict(self.progress),
            "errors": list(self.errors),

            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "elapsed": round(self.elapsed, 1),

            "result": (
                self.result.copy()
                if isinstance(self.result, dict)
                else self.result
            ),
        }

    def to_json(self) -> str:
        """Seguro para SSE / serialización JSON."""
        return json.dumps(
            self.to_dict(),
            default=str,
            ensure_ascii=False
        )


# ======================================================
# JOB MANAGER
# ======================================================

class JobManager:

    def __init__(
        self,
        max_workers: int = 2,
        job_ttl: int = 7200
    ):
        self._jobs: dict[str, Job] = {}

        # Reentrant lock -> evita deadlocks
        self._lock = threading.RLock()

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="job-worker"
        )

        # Tiempo de vida en RAM
        self._job_ttl = job_ttl

    # ======================================================
    # INTERNAL
    # ======================================================

    def _get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def _cleanup_expired_jobs(self):
        """Limpieza pasiva de memoria para jobs expirados."""

        now = time.time()
        expired = []

        # Copia defensiva para evitar RuntimeError
        for job_id, job in list(self._jobs.items()):
            if (
                job.completed_at
                and now - job.completed_at > self._job_ttl
            ):
                expired.append(job_id)

        for job_id in expired:
            del self._jobs[job_id]

    # ======================================================
    # CRUD JOBS
    # ======================================================

    def create_job(self, filename: str) -> Job:

        job = Job(
            id=secrets.token_hex(8),
            filename=filename
        )

        with self._lock:
            self._cleanup_expired_jobs()
            self._jobs[job.id] = job

        return job

    def get_job(self, job_id: str) -> Optional[Job]:

        with self._lock:
            self._cleanup_expired_jobs()
            return self._get_job(job_id)

    def list_jobs(self, limit: int = 20) -> list[Job]:

        with self._lock:
            self._cleanup_expired_jobs()

            jobs = list(self._jobs.values())

            jobs.sort(
                key=lambda j: j.created_at,
                reverse=True
            )

            return jobs[:limit]

    # ======================================================
    # UPDATE METHODS
    # ======================================================

    def update_progress(
        self,
        job_id: str,
        **kwargs
    ):
        with self._lock:

            job = self._get_job(job_id)

            if not job:
                return

            # No actualizar si ya fue cancelado
            if job.status == JobStatus.CANCELLED:
                return

            if "status" in kwargs:
                job.status = JobStatus(kwargs["status"])

            if "result" in kwargs:
                job.result = kwargs["result"]

            if "errors" in kwargs:
                job.errors = kwargs["errors"]

            if "progress" in kwargs:
                job.progress.update(kwargs["progress"])

            if job.status in (
                JobStatus.DONE,
                JobStatus.ERROR,
                JobStatus.CANCELLED
            ):
                job.completed_at = time.time()

            job.updated_at = time.time()
            job.progress_version += 1

    def update_phase(
        self,
        job_id: str,
        phase: str,
        **progress_kw
    ):
        with self._lock:

            job = self._get_job(job_id)

            if (
                not job
                or job.status == JobStatus.CANCELLED
            ):
                return

            job.progress["phase"] = phase
            job.progress.update(progress_kw)

            job.updated_at = time.time()
            job.progress_version += 1

    def set_result(
        self,
        job_id: str,
        result: dict
    ):
        with self._lock:

            job = self._get_job(job_id)

            if (
                not job
                or job.status == JobStatus.CANCELLED
            ):
                return

            job.result = result
            job.status = JobStatus.DONE

            job.progress.update({
                "pct": 100,
                "phase": "Completado"
            })

            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1

    def set_error(
        self,
        job_id: str,
        error: str
    ):
        with self._lock:

            job = self._get_job(job_id)

            if (
                not job
                or job.status == JobStatus.CANCELLED
            ):
                return

            job.errors.append(error)

            job.status = JobStatus.ERROR

            job.progress.update({
                "phase": "Error"
            })

            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1

    # ======================================================
    # EXECUTION
    # ======================================================

    def submit(
        self,
        job_id: str,
        fn: Callable,
        *args,
        **kwargs
    ):
        """
        Ejecuta una función en un hilo secundario
        con callback de progreso inyectado.
        """

        def progress_callback(
            pct: int,
            total_batches: int = 0,
            phase: Optional[str] = None,
            **extra_progress
        ):
            with self._lock:

                job = self._get_job(job_id)

                if not job:
                    return

                # Cooperative cancellation
                if job.status == JobStatus.CANCELLED:
                    raise JobCancelled(
                        "El trabajo fue cancelado."
                    )

                progress_data = {
                    "pct": pct,
                    "total_batches": total_batches,
                    **extra_progress
                }

                if phase:
                    progress_data["phase"] = phase

                job.progress.update(progress_data)

                job.updated_at = time.time()
                job.progress_version += 1

        def _run():

            try:
                # Verifica cancelación
                with self._lock:
                    job = self._get_job(job_id)

                    if (
                        job
                        and job.status == JobStatus.CANCELLED
                    ):
                        return

                self.update_progress(
                    job_id,
                    status=JobStatus.EXTRACTING
                )

                kwargs["progress_callback"] = progress_callback

                # Ejecutar proceso pesado
                result = fn(*args, **kwargs)

                # Fase opcional
                self.update_progress(
                    job_id,
                    status=JobStatus.POST_PROCESSING
                )

                # Validación final
                with self._lock:
                    job = self._get_job(job_id)

                    if (
                        job
                        and job.status == JobStatus.CANCELLED
                    ):
                        return

                self.set_result(
                    job_id,
                    result
                )

            except JobCancelled:

                log.info(
                    "Job %s cancelado limpiamente.",
                    job_id
                )

            except Exception:

                log.exception(
                    "Job %s falló durante ejecución.",
                    job_id
                )

                self.set_error(
                    job_id,
                    "Error interno durante la ejecución"
                )

        future = self._executor.submit(_run)

        with self._lock:

            job = self._get_job(job_id)

            if job:
                job.future = future

        return future

    # ======================================================
    # CONTROL
    # ======================================================

    def cancel_job(
        self,
        job_id: str
    ) -> bool:
        """
        Cancela un job en cola
        o solicita cancelación cooperativa
        de un job en ejecución.
        """

        with self._lock:

            job = self._get_job(job_id)

            if not job:
                return False

            cancelled = False

            # Solo funciona si sigue QUEUED
            if job.future:
                cancelled = job.future.cancel()

            if cancelled or job.status in (
                JobStatus.QUEUED,
                JobStatus.EXTRACTING,
                JobStatus.POST_PROCESSING
            ):

                job.status = JobStatus.CANCELLED

                job.progress.update({
                    "phase": "Cancelado"
                })

                job.completed_at = time.time()
                job.updated_at = time.time()
                job.progress_version += 1

                return True

            return False

    def shutdown(
        self,
        wait: bool = True
    ):
        self._executor.shutdown(wait=wait)


# ======================================================
# GLOBAL INSTANCE
# ======================================================

job_manager = JobManager()