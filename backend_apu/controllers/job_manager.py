import uuid
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger("mapus.jobs")


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    POST_PROCESSING = "POST_PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"


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
    errors: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    progress_version: int = 0

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": self.progress,
            "errors": self.errors,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "elapsed": round(self.elapsed, 1),
            "result": self.result,
        }


class JobManager:
    def __init__(self, max_workers: int = 2, job_ttl: int = 7200):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._job_ttl = job_ttl
        self._subscribers: dict[str, list] = {}
        self._sub_lock = threading.Lock()

    def create_job(self, filename: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.DONE and job.completed_at:
                if time.time() - job.completed_at > self._job_ttl:
                    del self._jobs[job_id]
                    return None
            return job

    def update_progress(self, job_id: str, **kwargs):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if "status" in kwargs:
                job.status = JobStatus(kwargs["status"])
            if "result" in kwargs:
                job.result = kwargs["result"]
            if "errors" in kwargs:
                job.errors = kwargs["errors"]
            if "progress" in kwargs:
                job.progress.update(kwargs["progress"])
            if kwargs.get("status") == JobStatus.DONE:
                job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1

    def update_phase(self, job_id: str, phase: str, **progress_kw):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress["phase"] = phase
            job.progress.update(progress_kw)
            job.updated_at = time.time()
            job.progress_version += 1

    def set_result(self, job_id: str, result: dict):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.result = result
            job.status = JobStatus.DONE
            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1

    def set_error(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.errors.append(error)
            job.status = JobStatus.ERROR
            job.completed_at = time.time()
            job.updated_at = time.time()
            job.progress_version += 1

    def add_error(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.errors.append(error)
            job.updated_at = time.time()
            job.progress_version += 1

    def list_jobs(self, limit: int = 20) -> list[Job]:
        with self._lock:
            now = time.time()
            active = []
            for j in list(self._jobs.values()):
                if j.status in (JobStatus.QUEUED, JobStatus.EXTRACTING, JobStatus.POST_PROCESSING):
                    active.append(j)
                elif j.completed_at and now - j.completed_at > self._job_ttl:
                    continue
                else:
                    active.append(j)
            active.sort(key=lambda j: j.created_at, reverse=True)
            return active[:limit]

    def submit_job(self, job_id: str, fn, *args, **kwargs):
        def _run():
            try:
                fn(job_id, *args, **kwargs)
            except Exception as e:
                log.error("Job %s failed: %s", job_id, e)
                self.set_error(job_id, str(e))
        self._executor.submit(_run)


job_manager = JobManager()
