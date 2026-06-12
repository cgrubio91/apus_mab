"""
Application: Query APUs Use Case
Orchestrates listing, filtering, dashboard stats, and project deletion.
"""

import logging
from typing import Optional

from src.infrastructure.database.repositories.apu_repository import apu_repo

log = logging.getLogger("mapus.application.query_apus")

ALLOWED_SORT_FIELDS = sorted(apu_repo._allowed_sort_fields)
MAX_LIMIT = apu_repo._max_limit


def get_apus(
    filters: dict,
    limit: int = 50,
    offset: int = 0,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    search: Optional[str] = None,
) -> dict:
    return apu_repo.get_apus(filters, limit, offset, sort_by, sort_order, search)


def get_filter_options() -> dict[str, list[str]]:
    return apu_repo.get_filter_options()


def get_dashboard_stats() -> dict:
    return apu_repo.get_dashboard_stats()


def get_unique_projects() -> list[str]:
    return apu_repo.get_unique_projects()


def delete_project(nombre_proyecto: str) -> dict:
    return apu_repo.delete_project_apus(nombre_proyecto)


def save_extracted(payload: list[dict]):
    return apu_repo.insert_apus_stream(payload)
