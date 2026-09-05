"""
Infrastructure: Scheduler de Fondo Automático
Ejecuta tareas periódicas no bloqueantes para mantener al día los índices DANE (ICCP)
y referencias de precios de contratos públicos (SECOP II y ANI).
"""

import asyncio
import logging
from typing import Optional

log = logging.getLogger("mapus.scheduler")

_task: Optional[asyncio.Task] = None
_running: bool = False

# Intervalo por defecto: 12 horas (en segundos)
INTERVALO_SEGUNDOS = 43200


async def _ejecutar_ciclo_actualizacion():
    """Ejecuta una ronda de actualización de índices y referencias externas."""
    log.info("Iniciando ciclo programado de sincronización de índices y referencias...")

    # 1. Actualizar serie DANE ICCP
    try:
        from src.config.settings import settings
        if settings.DANE_ICCP_DATASET_ID:
            from src.application.use_cases.indices_costos import ingerir_dane
            resultado_dane = await asyncio.to_thread(
                ingerir_dane,
                settings.DANE_ICCP_DATASET_ID,
                settings.DANE_ICCP_SERIE or "ICCP",
            )
            log.info(
                "Sincronización DANE completada: %s puntos / %s registros afectados.",
                resultado_dane.get("puntos", 0),
                resultado_dane.get("afectados", 0),
            )
        else:
            log.info("DANE_ICCP_DATASET_ID no configurado; omitiendo sincronización DANE automática.")
    except Exception:
        log.warning("No se pudo actualizar el índice DANE en este ciclo", exc_info=True)

    # 2. Ingesta ligera de contratos recientes SECOP II
    try:
        from src.application.use_cases.ingesta_referencias import ingerir_secop
        for kw in ["pavimento", "concreto", "interventoría"]:
            try:
                res_secop = await asyncio.to_thread(ingerir_secop, kw, limite=15)
                log.info("Sincronización SECOP II ('%s'): %s contratos.", kw, res_secop.get("registros", 0))
            except Exception:
                pass
    except Exception:
        log.warning("No se pudo actualizar SECOP II en este ciclo", exc_info=True)

    # 3. Ingesta ligera de concesiones ANI
    try:
        from src.application.use_cases.ingesta_referencias import ingerir_ani
        res_ani = await asyncio.to_thread(ingerir_ani, "vial", limite=20)
        log.info("Sincronización ANI completada: %s contratos.", res_ani.get("registros", 0))
    except Exception:
        log.warning("No se pudo actualizar ANI en este ciclo", exc_info=True)

    log.info("Ciclo de sincronización programado finalizado exitosamente.")


async def _scheduler_loop():
    """Bucle infinito del scheduler con espera inicial para no entorpecer el arranque."""
    # Espera 30 segundos tras el arranque de FastAPI
    await asyncio.sleep(30)
    while _running:
        try:
            await _ejecutar_ciclo_actualizacion()
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error en ciclo del scheduler automático")

        try:
            await asyncio.sleep(INTERVALO_SEGUNDOS)
        except asyncio.CancelledError:
            break


def start_background_scheduler():
    """Inicia el scheduler en segundo plano si no está activo."""
    global _task, _running
    if _running:
        return
    _running = True
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_scheduler_loop())
    log.info("Scheduler de actualización automática iniciado en background.")


def stop_background_scheduler():
    """Detiene el scheduler de forma segura."""
    global _task, _running
    _running = False
    if _task and not _task.done():
        _task.cancel()
        log.info("Scheduler de actualización automática detenido.")
