"""
Presentation: Notificaciones web por rol.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.application.use_cases.notificaciones import (
    get_notificaciones,
    marcar_leida,
    marcar_todas_leidas,
)
from src.presentation.auth import get_current_user

log = logging.getLogger("mapus.presentation.notificaciones")
router = APIRouter()


@router.get("/notificaciones", tags=["Notificaciones"])
async def listar_notificaciones(user: dict = Depends(get_current_user)) -> dict:
    try:
        return {"success": True, **get_notificaciones(user)}
    except Exception:
        log.exception("Error listando notificaciones")
        raise HTTPException(status_code=500, detail="Error interno del servidor. Revisa los logs para más detalle.")


@router.post("/notificaciones/{notificacion_id}/leer", tags=["Notificaciones"])
async def leer_notificacion(notificacion_id: int, user: dict = Depends(get_current_user)) -> dict:
    try:
        marcar_leida(user["id"], notificacion_id)
        return {"success": True}
    except Exception:
        log.exception("Error marcando notificación %s", notificacion_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor. Revisa los logs para más detalle.")


@router.post("/notificaciones/leer-todas", tags=["Notificaciones"])
async def leer_todas(user: dict = Depends(get_current_user)) -> dict:
    try:
        marcar_todas_leidas(user)
        return {"success": True}
    except Exception:
        log.exception("Error marcando todas las notificaciones")
        raise HTTPException(status_code=500, detail="Error interno del servidor. Revisa los logs para más detalle.")
