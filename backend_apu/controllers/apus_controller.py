import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, Depends, HTTPException, status
from psycopg2 import Error as DatabaseError
from pydantic import BaseModel

from db_config import execute_query
from ..models.apu import ApuRecord, ApuFilters
from ..services.apu_service import apu_service

log = logging.getLogger("mapus.backend.apus")
router = APIRouter()

ALLOWED_SORT_FIELDS = sorted(apu_service._allowed_sort_fields)
MAX_LIMIT = apu_service._max_limit
get_apus = apu_service.get_apus
ApuResponse = None  # used as response_model but we handle it differently


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
):
    try:
        filters = {k: v for k, v in filters_params.model_dump().items() if v is not None}

        result = await asyncio.to_thread(
            get_apus,
            filters,
            limit,
            offset,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
        )

        log.info("APU query executed smoothly", extra={
            "filters": filters,
            "limit": limit,
            "offset": offset,
            "search_term": search,
            "result_count": len(result.get("data", [])) if isinstance(result, dict) else 0,
        })

        return result

    except DatabaseError as dbe:
        log.error("Database syntax or connection error in get_apus: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar la consulta en la base de datos.",
        )
    except Exception:
        log.exception("Critical unexpected error in get_apus_endpoint")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error interno al recuperar los registros.",
        )


@router.get("/apus/filter-options", tags=["APUs"])
async def get_apus_filter_options():
    try:
        return apu_service.get_filter_options()
    except DatabaseError as dbe:
        log.error("Database error in get_apus_filter_options: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cargar las opciones de filtro.",
        )


@router.get("/dashboard", tags=["APUs"])
async def get_dashboard_stats_endpoint():
    try:
        return apu_service.get_dashboard_stats()
    except DatabaseError as dbe:
        log.error("Database error in get_dashboard_stats: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cargar las métricas del dashboard.",
        )


@router.get("/projects", tags=["APUs"])
async def get_projects():
    try:
        return {"projects": apu_service.get_unique_projects()}
    except DatabaseError as dbe:
        log.error("Database error in get_projects: %s", dbe)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cargar la lista de proyectos.",
        )