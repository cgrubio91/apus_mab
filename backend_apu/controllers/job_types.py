"""
Job Types — Compatibility Wrapper
All logic now lives in src/domain/entities/job.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.domain.entities.job import Job, JobStatus, JobCancelled

__all__ = ["Job", "JobStatus", "JobCancelled"]
