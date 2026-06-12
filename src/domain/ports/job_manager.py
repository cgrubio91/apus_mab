from abc import ABC, abstractmethod
from typing import Optional, Callable
from src.domain.entities.job import Job, JobStatus


class JobManagerPort(ABC):

    @abstractmethod
    def create_job(self, filename: str) -> Job:
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        ...

    @abstractmethod
    def list_jobs(self, limit: int = 20) -> list[Job]:
        ...

    @abstractmethod
    def update_progress(self, job_id: str, **kwargs):
        ...

    @abstractmethod
    def update_phase(self, job_id: str, phase: str, **progress_kw):
        ...

    @abstractmethod
    def set_result(self, job_id: str, result: dict):
        ...

    @abstractmethod
    def set_error(self, job_id: str, error: str):
        ...

    @abstractmethod
    def submit(self, job_id: str, fn: Callable, *args, **kwargs):
        ...

    @abstractmethod
    def submit_job(self, job_id: str, fn: Callable, *args):
        ...

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        ...
