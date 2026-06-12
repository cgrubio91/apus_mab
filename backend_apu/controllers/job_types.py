import json
import time
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from concurrent.futures import Future


class JobCancelled(Exception):
    """Excepción controlada para detener jobs cancelados."""
    pass


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    POST_PROCESSING = "POST_PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


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

    future: Optional[Future] = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict[str, Any]:
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
            "result": (
                self.result.copy()
                if isinstance(self.result, dict)
                else self.result
            ),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            default=str,
            ensure_ascii=False
        )
