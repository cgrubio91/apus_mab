import json
import time
import threading
import logging
import secrets

from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable, Dict, List

log = logging.getLogger("mapus.backend.jobs")

# ==========================================================
# EXCEPTIONS & ENUMS
# ==========================================================

class JobCancelled(Exception):
    """Excepción controlada para abortar hilos de extracción cancelados."""
    pass


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    POST_PROCESSING = "POST_PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


# ==========================================================
# JOB MODEL (Dataclass Fuertemente Tipada)
# ==========================================================

@dataclass
class Job:
    id: str
    filename: str
    status: JobStatus = JobStatus.QUEUED
    
    progress: Dict[str, Any] = field(default_factory=lambda: {
        "phase": "En cola...",
        "current_batch": 0,
        "total_batches": 0,
        "current_page": 0,
        "total_pages": 0,
        "percent": 0
    })
    
    result: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    progress_version: int = 0
    
    # Almacena la referencia del Future para cancelaciones en cola
    future: Optional[Future] = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def _serialize_obj(self, obj: Any) -> Any:
        """CORRECCIÓN: Convierte objetos complejos (Decimal, date) a JSON nativo sin romper tipos."""
        from decimal import Decimal
        from datetime import date, datetime
                
        if obj is None:
            return None
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
        if isinstance(obj, dict):
            return {k: self._serialize_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize_obj(item) for item in obj]
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """Genera una copia defensiva profunda para evitar colisiones en hilos concurrentes."""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": dict(self.progress),
            "errors": list(self.errors),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "elapsed": round(self.elapsed, 1),
            "result": self._serialize_obj(self.result)
        }

    def to_json(self) -> str:
        """Serialización ultra-segura para canales Server-Sent Events (SSE)."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ==========================================================
# JOB ORQUESTRATOR (JobManager)
# ==========================================================

class JobManager:
    def __init__(self, max_workers: int = 2, job_ttl_hours: int = 24):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mapus-worker"
        )
        self._job_ttl_seconds = job_ttl_hours * 3600

    def _get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def cleanup_old_jobs(self):
        """Recolector de basura reactivo en memoria RAM."""
        now = time.time()
        expired_ids = []
        
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.completed_at and (now - job.completed_at > self._job_ttl_seconds):
                    expired_ids.append(job_id)
            
            for job_id in expired_ids:
                del self._jobs[job_id]
                log.info("Garbage Collector: Job %s purgado de la memoria RAM", job_id)

    def create_job(self, filename: str) -> Job:
        job = Job(
            id=secrets.token_hex(8),
            filename=filename
        )
        with self._lock:
            self.cleanup_old_jobs()
            self._jobs[job.id] = job
        log.info("Created job %s for file %s", job.id, filename)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            self.cleanup_old_jobs()
            return self._get_job(job_id)

    def get_all_jobs(self) -> List[Job]:
        with self._lock:
            self.cleanup_old_jobs()
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update_progress(self, job_id: str, current: int, total: int, phase: str):
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return

            job.status = JobStatus.EXTRACTING
            job.progress["current_batch"] = current
            job.progress["total_batches"] = total
            job.progress["phase"] = phase
            job.progress["percent"] = int((current / total) * 100) if total > 0 else 0
            job.updated_at = time.time()
            job.progress_version += 1

    def update_phase(self, job_id: str, phase: str, **kwargs):
        """CORRECCIÓN: Permite alterar la fase visual y opcionalmente el status de forma dinámica."""
        status = kwargs.pop('status', None)
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            
            job.progress["phase"] = phase
            job.progress.update(kwargs)
            
            if status:
                job.status = status
                
            job.updated_at = time.time()
            job.progress_version += 1

    def submit(self, job_id: str, func: Callable, *args, **kwargs):
        job = self.get_job(job_id)
        if not job:
            log.error("Submit fallido: Job %s no existe en el sistema", job_id)
            return

        def progress_callback(current: int, total: int, phase: str, **extra):
            with self._lock:
                current_job = self._get_job(job_id)
                if not current_job:
                    return
                
                if current_job.status == JobStatus.CANCELLED:
                    raise JobCancelled("Cancelación solicitada por el usuario.")
                
                self.update_progress(job_id, current, total, phase)
                if extra:
                    current_job.progress.update(extra)

        def _run():
            try:
                with self._lock:
                    current_job = self._get_job(job_id)
                    if current_job and current_job.status == JobStatus.CANCELLED:
                        return

                self.update_phase(job_id, "Iniciando extracción...", status=JobStatus.EXTRACTING)
                kwargs['progress_callback'] = progress_callback

                result = func(*args, **kwargs)

                with self._lock:
                    current_job = self._get_job(job_id)
                    if current_job and current_job.status == JobStatus.CANCELLED:
                        return
                    
                    current_job.result = result
                    current_job.status = JobStatus.DONE
                    current_job.progress["phase"] = "Completado"
                    current_job.progress["percent"] = 100
                    current_job.completed_at = time.time()
                    current_job.updated_at = time.time()
                    current_job.progress_version += 1
                
                log.info("Job %s terminado con éxito", job_id)

            except JobCancelled:
                log.info("Job %s interrumpido y abortado limpiamente por el usuario", job_id)
            except Exception as e:
                log.exception("Error crítico ejecutando el hilo de la tarea %s", job_id)
                with self._lock:
                    current_job = self._get_job(job_id)
                    if current_job and current_job.status != JobStatus.CANCELLED:
                        current_job.status = JobStatus.ERROR
                        current_job.errors.append(str(e))
                        current_job.progress["phase"] = "Error en el procesamiento"
                        current_job.completed_at = time.time()
                        current_job.updated_at = time.time()
                        current_job.progress_version += 1

        future = self._executor.submit(_run)
        with self._lock:
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
                job.progress["phase"] = "Cancelado"
                job.completed_at = time.time()
                job.updated_at = time.time()
                job.progress_version += 1
                return True
            
            return False

    def shutdown(self, wait: bool = True):
        """CORRECCIÓN: Cierra el executor correctamente liberando los hilos en los reinicios."""
        log.info("Shutting down job manager (wait=%s)", wait)
        self._executor.shutdown(wait=wait)


# Instancia de orquestación global
job_manager = JobManager()