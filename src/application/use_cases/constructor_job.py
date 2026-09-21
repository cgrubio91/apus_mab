"""Application: Constructor de APU — generación de la propuesta en segundo plano.

Proponer la estructura tarda: la IA puede quedarse esperando a Gemini y, además,
se consultan CYPE, el catálogo comercial y el banco. Con una petición HTTP
normal el usuario queda atado a la pantalla y el navegador puede cortar antes de
recibir la respuesta.

Aquí la propuesta se calcula en un job del `job_manager` (el mismo mecanismo de
la extracción de archivos): el endpoint responde de inmediato con un `job_id`, el
usuario puede irse a otra vista, y al terminar se crea una notificación para que
la campana avise.
"""

import logging
from typing import Optional

from src.application.use_cases import constructor_apu
from src.application.use_cases.notificaciones import crear_notificacion
from src.infrastructure.jobs.manager import job_manager

log = logging.getLogger("mapus.application.constructor_job")

# Prefijo del `filename` del job: permite recuperar el job de una solicitud sin
# depender de que el frontend conserve el id (p.ej. tras recargar la página).
PREFIJO_JOB = "constructor-apu"


def nombre_job(solicitud_id: int) -> str:
    return f"{PREFIJO_JOB}:{solicitud_id}"


def solicitud_de_job(filename: Optional[str]) -> Optional[int]:
    """Id de solicitud codificado en el nombre del job, si lo tiene."""
    if not filename or not str(filename).startswith(f"{PREFIJO_JOB}:"):
        return None
    try:
        return int(str(filename).split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def generar_propuesta_en_job(job_id: str, solicitud_id: int,
                             porcentajes_aiu: Optional[dict] = None,
                             rol_destino: str = "analista",
                             actividad: str = "") -> dict:
    """Genera la propuesta y notifica el desenlace. La ejecuta el worker del job."""
    job_manager.update_phase(job_id, "Consultando banco y proponiendo estructura con IA", pct=10)
    try:
        propuesta = constructor_apu.sugerir_estructura(solicitud_id, porcentajes_aiu=porcentajes_aiu)
    except Exception as e:
        # El job queda en error (lo marca el manager); además se avisa en la campana,
        # porque el usuario pudo haberse ido de la pantalla.
        _notificar(
            rol_destino, solicitud_id,
            titulo=f"No se pudo generar la propuesta del APU #{solicitud_id}",
            mensaje=(f"La IA no logró proponer la estructura de «{actividad or 'la actividad'}». "
                     "Vuelve al Constructor de APU e intenta de nuevo."),
            sufijo_clave="error",
        )
        log.warning("Job %s: fallo generando la propuesta de la solicitud %s: %s", job_id, solicitud_id, e)
        raise

    # `submit_job` ignora el valor de retorno, así que el resultado se guarda aquí:
    # es lo que el frontend recupera al volver a la pantalla.
    job_manager.set_result(job_id, propuesta)

    insumos = len((propuesta or {}).get("propuesta", {}).get("insumos") or [])
    _notificar(
        rol_destino, solicitud_id,
        titulo=f"Propuesta lista: APU #{solicitud_id}",
        mensaje=(f"La IA propuso {insumos} insumo(s) para «{actividad or 'la actividad'}». "
                 "Ábrela en el Constructor de APU para revisarla."),
        sufijo_clave="ok",
    )
    return propuesta


def _notificar(rol_destino: str, solicitud_id: int, titulo: str, mensaje: str, sufijo_clave: str) -> None:
    crear_notificacion(
        rol_destino=rol_destino,
        titulo=titulo,
        mensaje=mensaje,
        tipo="constructor",
        solicitud_id=solicitud_id,
        # Evita duplicar la notificación si se relanza la generación del mismo borrador.
        clave_unica=f"constructor:{solicitud_id}:{sufijo_clave}",
    )


def lanzar_generacion(solicitud_id: int, porcentajes_aiu: Optional[dict] = None,
                      rol_destino: str = "analista", actividad: str = "") -> str:
    """Encola la generación y devuelve el id del job."""
    job = job_manager.create_job(nombre_job(solicitud_id))
    # submit_job antepone el job_id al llamar a la función, no hay que repetirlo.
    job_manager.submit_job(
        job.id, generar_propuesta_en_job,
        solicitud_id, porcentajes_aiu, rol_destino, actividad,
    )
    log.info("Job %s encolado: propuesta IA para la solicitud %s", job.id, solicitud_id)
    return job.id


def job_de_solicitud(solicitud_id: int) -> Optional[dict]:
    """Job más reciente de una solicitud, para retomar tras recargar la página."""
    objetivo = nombre_job(solicitud_id)
    for job in job_manager.list_jobs(limit=100):
        if job.filename == objetivo:
            return {
                "job_id": job.id,
                "status": job.status.value,
                "result": job.result,
                "error": "; ".join(job.errors) if job.errors else None,
            }
    return None
