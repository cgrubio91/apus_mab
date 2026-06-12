"""
Infrastructure: Job Manager (ThreadPool-based background jobs)
"""

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
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            self._cleanup_expired_jobs()
            return self._get_job(job_id)

    def list_jobs(self, limit: int = 20) -> list[Job]:
        with self._lock:
            self._cleanup_expired_jobs()
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def update_progress(self, job_id: str, **kwargs):
        with self._lock:
            job = self._get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            if "status" in kwargs:
                job.status = JobStatus(kwargs["status"])
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
                return True
            return False

    def shutdown(self, wait: bool = True):
        self._executor.shutdown(wait=wait)


job_manager = JobManager()
