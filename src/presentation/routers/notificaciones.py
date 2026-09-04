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
from src.presentation.auth import get_current_user, get_current_user_flexible

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


@router.get("/notificaciones/stream", tags=["Notificaciones"])
async def stream_notificaciones(user: dict = Depends(get_current_user_flexible)):
    """Server-Sent Events (SSE) para notificaciones en tiempo real por rol.
    Acepta JWT en Header Authorization o por query parameter ?token=."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        ultimo_conteo = None
        while True:
            try:
                data = await asyncio.to_thread(get_notificaciones, user)
                no_leidas = data.get("no_leidas", 0)

                # Si cambió el número de no leídas o es el primer mensaje, enviar payload
                if ultimo_conteo is None or no_leidas != ultimo_conteo:
                    ultimo_conteo = no_leidas
                    payload = json.dumps({"success": True, **data}, ensure_ascii=False)
                    yield f"event: notificaciones\ndata: {payload}\n\n"
                else:
                    # Keepalive para evitar cierre de socket por proxy/navegador
                    yield ": keepalive\n\n"

                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Error en loop de stream_notificaciones")
                await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
