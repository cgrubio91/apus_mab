"""
Application: Notificaciones web por rol.

Cada notificación va dirigida a un rol (rol_destino). Un usuario ve las
notificaciones de su rol (los admin ven todas). El estado de lectura es por
usuario (tabla notificaciones_leidas). Los recordatorios de fecha límite se
generan de forma perezosa al consultar, deduplicados por clave_unica.
"""

import logging
from datetime import date

from src.infrastructure.database.connection import execute_query

log = logging.getLogger("mapus.application.notificaciones")

# Rol que debe actuar según el estado actual de la solicitud (para recordatorios).
ROL_RESPONSABLE_POR_ESTADO = {
    "pendiente_analisis": "analista",
    "analizado": "analista",
    "nuevas_cotizaciones": "contraparte",
    "preaprobado": "subgerente",
    "aprobado_subgerente": "legal",
}

DIAS_ANTICIPACION_RECORDATORIO = 2
MAX_NOTIFICACIONES = 50


def crear_notificacion(
    rol_destino: str,
    titulo: str,
    mensaje: str,
    tipo: str = "flujo",
    solicitud_id: int | None = None,
    clave_unica: str | None = None,
) -> None:
    """Inserta una notificación. Nunca lanza: una notificación fallida no debe
    romper la acción de negocio que la origina."""
    try:
        execute_query(
            """INSERT IGNORE INTO notificaciones (rol_destino, titulo, mensaje, tipo, solicitud_id, clave_unica)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (rol_destino, titulo[:200], mensaje, tipo, solicitud_id, clave_unica),
            fetch=False,
        )
    except Exception:
        log.exception("No se pudo crear la notificación para rol %s", rol_destino)


def notificar_transicion(solicitud_id: int, nuevo_estado: str, actor_nombre: str = "") -> None:
    """Emite la notificación al rol del siguiente paso del flujo de aprobación."""
    por = f" (por {actor_nombre})" if actor_nombre else ""
    mensajes = {
        "analizado": (
            "analista",
            f"Solicitud #{solicitud_id} analizada",
            f"El análisis IA de la solicitud #{solicitud_id} está listo. Pendiente de preaprobación.",
        ),
        "preaprobado": (
            "subgerente",
            f"Solicitud #{solicitud_id} preaprobada",
            f"La solicitud #{solicitud_id} fue preaprobada{por} y espera tu aprobación como subgerente técnico.",
        ),
        "nuevas_cotizaciones": (
            "contraparte",
            f"Solicitud #{solicitud_id} rechazada",
            f"La solicitud #{solicitud_id} fue rechazada{por}. Se requieren nuevas cotizaciones.",
        ),
        "nuevas_cotizaciones_recibidas": (
            "analista",
            f"Nuevas cotizaciones en solicitud #{solicitud_id}",
            f"Se registraron nuevas cotizaciones para la solicitud #{solicitud_id}. Pendiente de nuevo análisis/preaprobación.",
        ),
        "aprobado_subgerente": (
            "legal",
            f"Solicitud #{solicitud_id} lista para firma legal",
            f"La solicitud #{solicitud_id} fue aprobada por subgerencia{por} y espera la firma legal.",
        ),
        "aprobado_legal": (
            "analista",
            f"Solicitud #{solicitud_id} incorporada al banco",
            f"La solicitud #{solicitud_id} recibió firma legal{por} y quedó incorporada al banco de APUs.",
        ),
    }
    entry = mensajes.get(nuevo_estado)
    if not entry:
        return
    rol, titulo, mensaje = entry
    crear_notificacion(rol, titulo, mensaje, tipo="flujo", solicitud_id=solicitud_id)


def _generar_recordatorios() -> None:
    """Crea recordatorios para solicitudes cuya fecha límite de aprobación está
    próxima o vencida y aún no terminan el flujo. Deduplicado por día."""
    try:
        rows = execute_query(
            """SELECT id, estado, fecha_limite_aprobacion FROM solicitudes_apu
               WHERE fecha_limite_aprobacion IS NOT NULL
                 AND estado NOT IN ('aprobado_legal')
                 AND fecha_limite_aprobacion <= DATE_ADD(CURRENT_DATE, INTERVAL %s DAY)""",
            (DIAS_ANTICIPACION_RECORDATORIO,),
        )
    except Exception:
        log.exception("No se pudieron consultar solicitudes para recordatorios")
        return

    hoy = date.today().isoformat()
    for s in rows or []:
        rol = ROL_RESPONSABLE_POR_ESTADO.get(s["estado"])
        if not rol:
            continue
        limite = s["fecha_limite_aprobacion"]
        vencida = str(limite) < hoy
        titulo = f"⏰ Solicitud #{s['id']} {'VENCIDA' if vencida else 'próxima a vencer'}"
        mensaje = (
            f"La solicitud #{s['id']} (estado: {s['estado']}) tiene fecha límite de aprobación {limite}. "
            + ("El plazo ya venció." if vencida else "Quedan pocos días para actuar.")
        )
        crear_notificacion(
            rol,
            titulo,
            mensaje,
            tipo="recordatorio",
            solicitud_id=s["id"],
            clave_unica=f"recordatorio:{s['id']}:{s['estado']}:{hoy}",
        )


def get_notificaciones(user: dict) -> dict:
    """Notificaciones visibles para el usuario según su rol (admin ve todas),
    con su estado de lectura y el conteo de no leídas."""
    _generar_recordatorios()

    rol = (user.get("rol") or "user").lower()
    user_id = user["id"]

    params: tuple
    if rol == "admin":
        where_rol = ""
        params = (user_id, MAX_NOTIFICACIONES)
    else:
        where_rol = "WHERE n.rol_destino = %s"
        params = (user_id, rol, MAX_NOTIFICACIONES)

    rows = execute_query(
        f"""SELECT n.id, n.rol_destino, n.titulo, n.mensaje, n.tipo, n.solicitud_id, n.created_at,
                   (l.usuario_id IS NOT NULL) AS leida
            FROM notificaciones n
            LEFT JOIN notificaciones_leidas l
              ON l.notificacion_id = n.id AND l.usuario_id = %s
            {where_rol}
            ORDER BY n.created_at DESC
            LIMIT %s""",
        params,
    ) or []

    for r in rows:
        r["leida"] = bool(r["leida"])
        if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()

    no_leidas = sum(1 for r in rows if not r["leida"])
    return {"notificaciones": rows, "no_leidas": no_leidas}


def marcar_leida(user_id: int, notificacion_id: int) -> None:
    execute_query(
        "INSERT IGNORE INTO notificaciones_leidas (notificacion_id, usuario_id) VALUES (%s, %s)",
        (notificacion_id, user_id),
        fetch=False,
    )


def marcar_todas_leidas(user: dict) -> None:
    rol = (user.get("rol") or "user").lower()
    if rol == "admin":
        execute_query(
            """INSERT IGNORE INTO notificaciones_leidas (notificacion_id, usuario_id)
               SELECT n.id, %s FROM notificaciones n""",
            (user["id"],),
            fetch=False,
        )
    else:
        execute_query(
            """INSERT IGNORE INTO notificaciones_leidas (notificacion_id, usuario_id)
               SELECT n.id, %s FROM notificaciones n WHERE n.rol_destino = %s""",
            (user["id"], rol),
            fetch=False,
        )
