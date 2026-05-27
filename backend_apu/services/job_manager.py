import logging
import uuid
import time
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("mapus.backend.jobs")

@dataclass
class Job:
    id: str
    filename: str
    status: str = "QUEUED"  # QUEUED, EXTRACTING, POST_PROCESSING, DONE, ERROR
    progress: Dict[str, Any] = field(default_factory=lambda: {
        "current_batch": 0,
        "total_batches": 0,
        "phase": "En cola...",
        "percent": 0
    })
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Safe JSON-serializable dict representation."""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "progress": dict(self.progress),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_json(self) -> str:
        """Safe JSON string."""
        return json.dumps(self.to_dict())


class JobManager:
    def __init__(self, max_workers=2):
        self._jobs: Dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        
    def create_job(self, filename: str) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, filename=filename)
        self._jobs[job_id] = job
        log.info("Created job %s for file %s", job_id, filename)
        return job
        
    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)
        
    def get_all_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        
    def update_progress(self, job_id: str, current: int, total: int, phase: str):
        job = self.get_job(job_id)
        if job:
            job.status = "EXTRACTING"
            job.progress["current_batch"] = current
            job.progress["total_batches"] = total
            job.progress["phase"] = phase
            job.progress["percent"] = int((current / total) * 100) if total > 0 else 0
            job.updated_at = time.time()
            log.info("Job %s progress: %s (%d/%d) %d%%", job_id, phase, current, total, job.progress["percent"])

    def submit(self, job_id: str, func, *args, **kwargs):
        def _wrapper():
            job = self.get_job(job_id)
            if not job:
                log.error("Job %s not found in wrapper", job_id)
                return
            
            try:
                log.info("Job %s: Starting extraction for %s", job_id, job.filename)
                job.status = "EXTRACTING"
                job.progress["phase"] = "Iniciando extracción..."
                job.updated_at = time.time()
                
                # Pass the progress callback to the function
                kwargs['progress_callback'] = lambda current, total, phase: self.update_progress(job_id, current, total, phase)
                
                log.info("Job %s: Calling extraction function...", job_id)
                result = func(*args, **kwargs)
                log.info("Job %s: Extraction function returned, result count: %s", job_id, result.get("count", "?") if isinstance(result, dict) else "?")
                
                job.status = "POST_PROCESSING"
                job.progress["phase"] = "Procesamiento final y guardado..."
                job.progress["percent"] = 99
                job.updated_at = time.time()
                
                job.result = result
                job.status = "DONE"
                job.progress["phase"] = "Completado"
                job.progress["percent"] = 100
                log.info("Job %s: DONE successfully", job_id)
            except Exception as e:
                log.error("Job %s failed: %s", job_id, e, exc_info=True)
                job.status = "ERROR"
                job.error = str(e)
                job.progress["phase"] = f"Error: {e}"
            finally:
                job.updated_at = time.time()
                
        log.info("Job %s: Submitting to thread pool", job_id)
        self._executor.submit(_wrapper)
        return job_id

# Singleton instance
job_manager = JobManager()
