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
    backfill_desde_secop,
    estadisticas_insumo,
)
from src.application.use_cases.ingesta_referencias import (
    consultar_referencias,
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


@router.post("/catalogo/backfill")
async def backfill_catalogo_endpoint(
    origen: str = Query("banco", pattern="^(banco|secop)$"),
    limite: Optional[int] = Query(None, ge=1),
    user: dict = Depends(require_role("analista")),
) -> dict:
    try:
        if origen == "secop":
            return backfill_desde_secop(limite=limite)
        return backfill_desde_banco(limite=limite)
    except Exception as e:
        log.exception("Error en backfill del catálogo (%s)", origen)
        raise HTTPException(status_code=500, detail=f"Fallo en backfill: {e}")
