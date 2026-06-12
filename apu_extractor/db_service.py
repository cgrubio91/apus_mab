"""
🗃️ DB Service — Compatibility Wrapper
All logic now lives in src/infrastructure/database/repositories/apu_repository.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.database.repositories.apu_repository import (
    insert_apus_batch,
    insert_apus_stream,
    get_unique_projects,
    get_apus,
    get_dashboard_stats,
    delete_project_apus,
    apu_repo,
)

__all__ = [
    "insert_apus_batch", "insert_apus_stream",
    "get_unique_projects", "get_apus",
    "get_dashboard_stats", "delete_project_apus",
    "apu_repo",
]
