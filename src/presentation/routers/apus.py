"""
Presentation: APU Query Routes
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, Depends, HTTPException, status
from psycopg2 import Error as DatabaseError
from pydantic import BaseModel

from src.application.use_cases.query_apus import (
    get_apus as query_apus,
    get_filter_options,
    get_dashboard_stats,
    get_unique_projects,
    delete_project,
    ALLOWED_SORT_FIELDS,
    MAX_LIMIT,
)

log = logging.getLogger("mapus.presentation.apus")
router = APIRouter()


class ApuQueryFilters(BaseModel):
    nombre_proyecto: Optional[str] = None
    ciudad: Optional[str] = None
    items_descripcion: Optional[str] = None
    insumo_descripcion: Optional[str] = None
    tipo_insumo: Optional[str] = None
    contratista: Optional[str] = None
    entidad: Optional[str] = None
    codigo_insumo: Optional[str] = None
    item: Optional[str] = None
    item_unidad: Optional[str] = None
    insumo_unidad: Optional[str] = None
    pais: Optional[str] = None
    numero_contrato: Optional[str] = None


@router.get("/apus", tags=["APUs"])
async def get_apus_endpoint(
    filters_params: ApuQueryFilters = Depends(),
    search: Optional[str] = Query(None, pattern=r"^[a-zA-Z0-9\s\-_.,\+áéíóúÁÉÍÓÚñÑ]+$"),
    sort_by: Optional[str] = Query(None, pattern=f"^({'|'.join(ALLOWED_SORT_FIELDS)})$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    try:
        filters = {k: v for k, v in filters_params.model_dump().items() if v is not None}
        result = await asyncio.to_thread(query_apus, filters, limit, offset, sort_by=sort_by, sort_order=sort_order, search=search)
        return result
    except DatabaseError:
        log.exception("Database error in get_apus")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar la consulta en la base de datos.")
    except Exception:
        log.exception("Critical error in get_apus_endpoint")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error interno al recuperar los registros.")


@router.get("/apus/filter-options", tags=["APUs"])
async def get_apus_filter_options() -> dict:
    try:
        return get_filter_options()
    except DatabaseError:
        log.exception("Database error in get_apus_filter_options")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al cargar las opciones de filtro.")


@router.get("/dashboard", tags=["APUs"])
async def get_dashboard_stats_endpoint() -> dict:
    try:
        return get_dashboard_stats()
    except DatabaseError:
        log.exception("Database error in get_dashboard_stats")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al cargar las métricas del dashboard.")


@router.get("/projects", tags=["APUs"])
async def get_projects() -> dict:
    try:
        return {"projects": get_unique_projects()}
    except DatabaseError:
        log.exception("Database error in get_projects")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al cargar la lista de proyectos.")


@router.delete("/projects", tags=["APUs"])
async def delete_projects(nombre_proyecto: str = Query(..., min_length=1)) -> dict:
    try:
        log.warning("Deleting project: %s", nombre_proyecto)
        return await asyncio.to_thread(delete_project, nombre_proyecto)
    except DatabaseError:
        log.exception("Database error in delete_projects")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al eliminar el proyecto.")
