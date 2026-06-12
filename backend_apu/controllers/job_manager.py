"""
Job Manager — Compatibility Wrapper
All logic now lives in src/infrastructure/jobs/manager.py and src/domain/entities/job.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.infrastructure.jobs.manager import JobManager, job_manager
from src.domain.entities.job import JobStatus

__all__ = ["JobManager", "job_manager", "JobStatus"]
