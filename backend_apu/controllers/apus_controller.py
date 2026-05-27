import logging

from fastapi import APIRouter, Query, HTTPException

from ..models.apu import ApuRecord, ApuFilters
from apu_extractor.db_service import get_filter_options as _get_filter_options

log = logging.getLogger("mapus.backend.apus")
router = APIRouter()

MAX_LIMIT = 500


@router.get("/projects")
async def get_projects():
    from apu_extractor import get_unique_projects
    try:
        projects = get_unique_projects()
        return {"projects": projects}
    except Exception as e:
        log.error("get_projects error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/apus")
async def get_apus_endpoint(
    nombre_proyecto: str = Query(None),
    ciudad: str = Query(None),
    items_descripcion: str = Query(None),
    insumo_descripcion: str = Query(None),
    tipo_insumo: str = Query(None),
    contratista: str = Query(None),
    entidad: str = Query(None),
    codigo_insumo: str = Query(None),
    item: str = Query(None),
    item_unidad: str = Query(None),
    insumo_unidad: str = Query(None),
    pais: str = Query(None),
    numero_contrato: str = Query(None),
    search: str = Query(None),
    sort_by: str = Query(None),
    sort_order: str = Query("asc"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    from apu_extractor import get_apus
    filters = {k: v for k, v in locals().items()
               if v is not None and k not in ("limit", "offset", "search", "sort_by", "sort_order")}
    try:
        return get_apus(filters, limit, offset, sort_by=sort_by, sort_order=sort_order, search=search)
    except Exception as e:
        log.error("get_apus error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects")
async def delete_project(nombre_proyecto: str = Query(..., min_length=1)):
    from apu_extractor import delete_project_apus
    log.warning("Deleting project: %s", nombre_proyecto)
    try:
        return delete_project_apus(nombre_proyecto)
    except Exception as e:
        log.error("delete_project error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/apus/filter-options")
async def apus_filter_options():
    try:
        return _get_filter_options()
    except Exception as e:
        log.error("get_filter_options error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def dashboard():
    from apu_extractor import get_dashboard_stats
    try:
        return get_dashboard_stats()
    except Exception as e:
        log.error("get_dashboard_stats error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))