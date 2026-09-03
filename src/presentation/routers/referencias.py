"""
Presentation: Referencias de precio externas (SECOP II, ...)

Endpoints para:
  - disparar la ingesta desde SECOP por término (rol analista+), y
  - consultar las referencias externas ya guardadas.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.use_cases.catalogo_insumos import (
    backfill_desde_banco,
    backfill_desde_referencias_externas,
    estadisticas_insumo,
)
from src.application.use_cases.indices_costos import (
    cargar_serie_manual,
    estadisticas_insumo_indexadas,
    ingerir_dane,
    series_disponibles,
)
from src.application.use_cases.ingesta_referencias import (
    consultar_referencias,
    ingerir_ani,
    ingerir_cype,
    ingerir_homecenter,
    ingerir_idu,
    ingerir_invias,
    ingerir_secop,
)
from src.presentation.auth import get_current_user, require_role

log = logging.getLogger("mapus.presentation.referencias")

router = APIRouter(prefix="/referencias", tags=["referencias-externas"])


class IngestaSecopRequest(BaseModel):
    keyword: str = Field(..., min_length=3, description="Término de búsqueda (objeto del contrato)")
    ciudad: Optional[str] = Field(None, description="Filtro de ciudad/municipio")
    desde_fecha: Optional[str] = Field(None, description="'YYYY-MM-DD' para acotar por recencia")
    limite: int = Field(200, ge=1, le=1000, description="Máximo de contratos a traer")


@router.post("/secop/ingerir")
async def ingerir_secop_endpoint(payload: IngestaSecopRequest,
                                 user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_secop(
            payload.keyword, ciudad=payload.ciudad,
            desde_fecha=payload.desde_fecha, limite=payload.limite,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo desde SECOP")
        raise HTTPException(status_code=502, detail=f"Fallo consultando SECOP: {e}")


class IngestaCypeRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Término de búsqueda de unidad de obra en CYPE")
    limite: int = Field(5, ge=1, le=20, description="Máximo de unidades a extraer")


@router.post("/cype/ingerir")
async def ingerir_cype_endpoint(payload: IngestaCypeRequest,
                                user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_cype(payload.query, limite=payload.limite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo desde CYPE")
        raise HTTPException(status_code=502, detail=f"Fallo consultando CYPE: {e}")


class IngestaHomecenterRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Término de búsqueda de material en Homecenter")
    limite: int = Field(5, ge=1, le=20, description="Máximo de materiales a traer")


@router.post("/homecenter/ingerir")
async def ingerir_homecenter_endpoint(payload: IngestaHomecenterRequest,
                                      user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_homecenter(payload.query, limite=payload.limite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo desde Homecenter")
        raise HTTPException(status_code=502, detail=f"Fallo consultando Homecenter: {e}")


class IngestaAniRequest(BaseModel):
    keyword: str = Field(..., min_length=3, description="Término de búsqueda en concesiones ANI")
    ciudad: Optional[str] = Field(None, description="Filtro de ciudad/municipio/tramo")
    limite: int = Field(200, ge=1, le=1000, description="Máximo de concesiones a traer")


@router.post("/ani/ingerir")
async def ingerir_ani_endpoint(payload: IngestaAniRequest,
                               user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_ani(payload.keyword, ciudad=payload.ciudad, limite=payload.limite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo desde ANI")
        raise HTTPException(status_code=502, detail=f"Fallo consultando ANI: {e}")


class IngestaDocumentalRequest(BaseModel):
    urls: Optional[list[str]] = Field(
        None, description="URLs de documentos (PDF/Excel). Si se omite, usa la lista-semilla del entorno")
    ciudad: Optional[str] = Field(None, description="Ciudad a asignar (IDU usa Bogotá por defecto)")
    fecha: Optional[str] = Field(None, description="'YYYY-MM-DD' de vigencia de la lista")


@router.post("/idu/ingerir")
async def ingerir_idu_endpoint(payload: IngestaDocumentalRequest,
                               user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_idu(urls=payload.urls, ciudad=payload.ciudad, fecha=payload.fecha)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo documentos IDU")
        raise HTTPException(status_code=502, detail=f"Fallo procesando documentos IDU: {e}")


@router.post("/invias/ingerir")
async def ingerir_invias_endpoint(payload: IngestaDocumentalRequest,
                                  user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_invias(urls=payload.urls, ciudad=payload.ciudad, fecha=payload.fecha)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo documentos INVÍAS")
        raise HTTPException(status_code=502, detail=f"Fallo procesando documentos INVÍAS: {e}")


@router.get("")
async def consultar_referencias_endpoint(
    descripcion: str = Query(..., min_length=3),
    fuente: Optional[str] = Query(None),
    ciudad: Optional[str] = Query(None),
    limite: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> dict:
    referencias = consultar_referencias(descripcion, fuente=fuente, ciudad=ciudad, limite=limite)
    return {"success": True, "count": len(referencias), "data": referencias}


# ── Catálogo canónico de insumos + histórico de precios ──


@router.get("/insumos/estadisticas")
async def estadisticas_insumo_endpoint(
    descripcion: str = Query(..., min_length=3),
    ciudad: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        return {"success": True, **estadisticas_insumo(descripcion, ciudad=ciudad)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/insumos/estadisticas-indexadas")
async def estadisticas_indexadas_endpoint(
    descripcion: str = Query(..., min_length=3),
    serie: str = Query("ICCP"),
    ciudad: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        return {"success": True, **estadisticas_insumo_indexadas(descripcion, serie, ciudad=ciudad)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Índices de costos (DANE) ──


class IngestaDaneRequest(BaseModel):
    dataset_id: str = Field(..., description="Dataset Socrata de la serie DANE")
    serie: str = Field("ICCP", description="Nombre con el que se guarda la serie")
    campo_periodo: Optional[str] = Field(None, description="Columna del periodo (autodetecta si se omite)")
    campo_valor: Optional[str] = Field(None, description="Columna del valor del índice (autodetecta si se omite)")
    where: Optional[str] = Field(None, description="Filtro SoQL opcional")


class CargarSerieRequest(BaseModel):
    serie: str = Field(..., description="Nombre de la serie")
    datos: dict = Field(..., description="{'YYYY-MM': valor, ...}")


@router.post("/indices/dane/ingerir")
async def ingerir_dane_endpoint(payload: IngestaDaneRequest,
                                user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return ingerir_dane(payload.dataset_id, payload.serie, campo_periodo=payload.campo_periodo,
                            campo_valor=payload.campo_valor, where=payload.where)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error ingiriendo serie DANE")
        raise HTTPException(status_code=502, detail=f"Fallo consultando DANE: {e}")


@router.post("/indices/cargar")
async def cargar_serie_endpoint(payload: CargarSerieRequest,
                                user: dict = Depends(require_role("analista"))) -> dict:
    try:
        return cargar_serie_manual(payload.serie, payload.datos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/indices")
async def series_disponibles_endpoint(user: dict = Depends(get_current_user)) -> dict:
    return {"success": True, "series": series_disponibles()}


@router.post("/catalogo/backfill")
async def backfill_catalogo_endpoint(
    origen: str = Query("banco", pattern="^(banco|externas)$"),
    limite: Optional[int] = Query(None, ge=1),
    user: dict = Depends(require_role("analista")),
) -> dict:
    """origen=banco: puebla desde la tabla apus. origen=externas: puebla desde
    TODAS las referencias externas ya ingeridas (SECOP, IDU, INVÍAS)."""
    try:
        if origen == "externas":
            return backfill_desde_referencias_externas(limite=limite)
        return backfill_desde_banco(limite=limite)
    except Exception as e:
        log.exception("Error en backfill del catálogo (%s)", origen)
        raise HTTPException(status_code=500, detail=f"Fallo en backfill: {e}")
