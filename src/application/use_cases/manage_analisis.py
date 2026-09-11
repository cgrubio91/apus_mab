"""
Application: Manage Análisis APU Use Case
Approval workflow orchestration: create, analyze, pre-approve, reject, approve.

Orquestador del flujo de aprobación. El motor de comparación contra el banco
vive en `analisis_comparacion` y los ayudantes de IA en `analisis_ia`; aquí se
re-exportan para mantener compatible la ruta histórica de importación.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from src.application.use_cases.notificaciones import notificar_transicion
from src.infrastructure.database.repositories.analisis_repository import analisis_repo
from src.application.use_cases.analisis_comparacion import (
    _agrupar_por_item,
    _analizar_apu_con_banco,
    _fijar_referencia,
    _marcar_equivalencias,
    _comparar_cotizaciones,
    _agrupar_insumos_texto,
    _comparar_proveedores,
    _generar_resumen_insumos,
    subir_insumo_al_banco,
)
from src.application.use_cases.analisis_ia import (
    _TIPOS_INSUMO_VALIDOS,
    _agrupar_insumos_ia,
    _analizar_insumos_proveedores,
    _confirmar_referencias_ia,
    _contexto_aprendizaje_rechazos,
    _resumen_insumos_para_ia,
    _analisis_apu_con_ia,
    _generar_resumen_ia,
)

log = logging.getLogger("mapus.application.analisis")

__all__ = [
    "ESTADOS",
    "_TIPOS_INSUMO_VALIDOS",
    "_detectar_modo",
    "crear_solicitud",
    "set_tipo_comparacion",
    "seleccionar_proyecto",
    "get_solicitudes",
    "get_solicitud",
    "realizar_analisis",
    "_agrupar_por_item",
    "_analizar_apu_con_banco",
    "_fijar_referencia",
    "_marcar_equivalencias",
    "_comparar_cotizaciones",
    "_agrupar_insumos_texto",
    "_agrupar_insumos_ia",
    "_analizar_insumos_proveedores",
    "_confirmar_referencias_ia",
    "subir_insumo_al_banco",
    "_comparar_proveedores",
    "_generar_resumen_insumos",
    "_contexto_aprendizaje_rechazos",
    "_resumen_insumos_para_ia",
    "_analisis_apu_con_ia",
    "_generar_resumen_ia",
    "preaprobar",
    "rechazar",
    "nuevas_cotizaciones_recibidas",
    "aprobar_subgerente",
    "firmar_legal",
    "_crear_items_presupuesto",
    "get_aprendizaje_rechazos",
    "eliminar_solicitud",
    "eliminar_solicitudes_lote",
]

ESTADOS = [
    "borrador",
    "pendiente_analisis",
    "analizado",
    "preaprobado",
    "rechazado",
    "nuevas_cotizaciones",
    "aprobado_subgerente",
    "aprobado_legal",
]


def _detectar_modo(insumos: list[dict]) -> str:
    """Adivina si la solicitud es un 'APU completo' (ítem + insumos con rendimiento)
    o 'solo insumos' (comparación de precios entre proveedores). El analista puede
    corregirlo luego con set_tipo_comparacion()."""
    if not insumos:
        return "apu"
    from collections import defaultdict
    por_item: dict = defaultdict(int)
    con_rendimiento = 0
    for ins in insumos:
        clave = (
            ins.get("grupo_cotizacion", 1),
            (ins.get("item") or "").strip(),
            (ins.get("items_descripcion") or "").strip(),
        )
        por_item[clave] += 1
        if ins.get("rendimiento_insumo") is not None:
            con_rendimiento += 1
    avg_insumos = len(insumos) / max(len(por_item), 1)
    frac_rendimiento = con_rendimiento / len(insumos)
    # Un APU tiene ítems descompuestos en varios insumos con rendimiento.
    return "apu" if (avg_insumos >= 2 and frac_rendimiento >= 0.3) else "insumos"


def crear_solicitud(grupos_insumos: list[dict], proyecto_id: Optional[int] = None) -> int:
    todos = []
    for grupo in grupos_insumos:
        gidx = grupo.get("grupo_cotizacion", 1)
        for ins in grupo.get("insumos", []):
            fila = dict(ins)
            fila.setdefault("grupo_cotizacion", gidx)
            todos.append(fila)
    tipo = _detectar_modo(todos)
    return analisis_repo.crear_solicitud(grupos_insumos, proyecto_id, tipo)


def set_tipo_comparacion(solicitud_id: int, tipo: str) -> dict:
    if tipo not in ("apu", "insumos"):
        raise ValueError("Tipo de comparación inválido (usa 'apu' o 'insumos')")
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") == "aprobado_legal":
        raise ValueError("No se puede cambiar el modo de una solicitud ya firmada legalmente")
    analisis_repo.actualizar_tipo_comparacion(solicitud_id, tipo)
    etiqueta = "APU completo" if tipo == "apu" else "Solo insumos (proveedores)"
    return {"success": True, "tipo_comparacion": tipo, "mensaje": f"Modo actualizado a: {etiqueta}."}


def seleccionar_proyecto(solicitud_id: int, proyecto_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") == "aprobado_legal":
        raise ValueError("No se puede cambiar el proyecto de una solicitud ya firmada legalmente")
    if not analisis_repo.existe_proyecto(proyecto_id):
        raise ValueError(f"Proyecto {proyecto_id} no encontrado")

    analisis_repo.actualizar_proyecto_id(solicitud_id, proyecto_id)
    return {"success": True, "mensaje": f"Proyecto #{proyecto_id} asignado a la solicitud #{solicitud_id}."}


def get_solicitudes(estado: Optional[str] = None) -> list:
    return analisis_repo.get_solicitudes(estado)


def get_solicitud(solicitud_id: int) -> Optional[dict]:
    return analisis_repo.get_solicitud(solicitud_id)


def realizar_analisis(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")

    insumos = solicitud.get("insumos", [])
    if not insumos:
        raise ValueError("La solicitud no tiene insumos para analizar")

    # Determina el modo: si no está fijado, se auto-detecta y se persiste.
    tipo = solicitud.get("tipo_comparacion")
    if not tipo:
        tipo = _detectar_modo(insumos)
        analisis_repo.actualizar_tipo_comparacion(solicitud_id, tipo)

    if tipo == "insumos":
        # Modo 'solo insumos': se comparan precios entre proveedores (no se crea ítem en el proyecto).
        insumos_comparados = _analizar_insumos_proveedores(insumos)
        # La IA confirma cuáles referencias del banco son realmente el mismo insumo.
        insumos_comparados = _confirmar_referencias_ia(insumos_comparados)
        comparacion_grupos = _comparar_proveedores(insumos)
        resumen, recomendacion = _generar_resumen_insumos(insumos_comparados, comparacion_grupos)
        analisis_json = json.dumps({
            "modo": "insumos",
            "items": [],
            "insumos_comparados": insumos_comparados,
            "comparacion_grupos": comparacion_grupos,
        }, default=str)
        items_analizados = []
    else:
        # Modo 'APU completo': la unidad de análisis es el ítem con sus insumos.
        apus_cotizados = _agrupar_por_item(insumos)
        items_analizados = [_analizar_apu_con_banco(apu) for apu in apus_cotizados]
        comparacion_grupos = _comparar_cotizaciones(items_analizados)
        resumen, recomendacion = _generar_resumen_ia(apus_cotizados, items_analizados, comparacion_grupos)
        analisis_json = json.dumps({
            "modo": "apu",
            "items": items_analizados,
            "comparacion_grupos": comparacion_grupos,
        }, default=str)

    analisis_repo.guardar_analisis(solicitud_id, analisis_json, resumen, recomendacion)
    analisis_repo.actualizar_estado(solicitud_id, "analizado")

    proyecto_id = solicitud.get("proyecto_id")
    if proyecto_id:
        proyecto_info = f"proyecto #{proyecto_id} (seleccionado manualmente)"
    else:
        nombre_proyecto = solicitud.get("nombre_proyecto", "")
        proyecto_id = analisis_repo.resolver_proyecto_por_nombre(nombre_proyecto)
        if proyecto_id:
            analisis_repo.actualizar_proyecto_id(solicitud_id, proyecto_id)
            proyecto_info = f"proyecto #{proyecto_id}"
        else:
            proyecto_info = "proyecto no identificado — selecciónalo manualmente antes de la firma legal"

    notificar_transicion(solicitud_id, "analizado")

    return {
        "solicitud_id": solicitud_id,
        "items_analizados": items_analizados,
        "resumen": resumen,
        "recomendacion": recomendacion,
        "proyecto_asignado": proyecto_info,
    }


def preaprobar(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "preaprobado", "AND estado = 'analizado'", conn=conn):
            raise ValueError("La solicitud no está en estado 'analizado'")
        analisis_repo.insertar_historial(solicitud_id, "preaprobado", usuario_rol, usuario_nombre, conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "pendiente_aprobacion_subgerente", usuario_rol, usuario_nombre, conn=conn)
        conn.commit()
        notificar_transicion(solicitud_id, "preaprobado", usuario_nombre)
        return {"success": True, "mensaje": "APU preaprobado. Enviado a subgerente técnico."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rechazar(solicitud_id: int, usuario_rol: str, usuario_nombre: str, motivo: str) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError("Solicitud no encontrada")
    estado_actual = solicitud.get("estado")
    if estado_actual not in ("analizado", "nuevas_cotizaciones"):
        raise ValueError(f"No se puede rechazar en estado '{estado_actual}'")

    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        fecha_limite = date.today() + timedelta(days=5)
        analisis_repo.actualizar_estado(solicitud_id, "nuevas_cotizaciones", conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "rechazado", usuario_rol, usuario_nombre, motivo, conn=conn)

        analisis = solicitud.get("analisis", {})
        if analisis and analisis.get("id"):
            analisis_repo.insertar_aprendizaje(analisis["id"], motivo, f"Rechazado por {usuario_rol}: {usuario_nombre}", conn=conn)

        conn.commit()
        notificar_transicion(solicitud_id, "nuevas_cotizaciones", usuario_nombre)
        return {"success": True, "mensaje": f"APU rechazado. Se solicitarán nuevas cotizaciones (límite: {fecha_limite}).", "fecha_limite": str(fecha_limite)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def nuevas_cotizaciones_recibidas(solicitud_id: int) -> dict:
    fecha_limite = date.today() + timedelta(days=3)
    if not analisis_repo.actualizar_estado(solicitud_id, "analizado"):
        raise ValueError("No se pudo actualizar el estado")
    analisis_repo.insertar_historial(solicitud_id, "nuevas_cotizaciones_recibidas", "contraparte", "Contraparte")
    notificar_transicion(solicitud_id, "nuevas_cotizaciones_recibidas")
    return {"success": True, "mensaje": f"Nuevas cotizaciones registradas. Plazo para aprobar: {fecha_limite}."}


def aprobar_subgerente(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "aprobado_subgerente", "AND estado = 'preaprobado'", conn=conn):
            raise ValueError("La solicitud no está en estado 'preaprobado'")
        analisis_repo.insertar_historial(solicitud_id, "aprobado_subgerente", usuario_rol, usuario_nombre, conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "pendiente_firma_legal", "sistema", "Sistema", conn=conn)
        conn.commit()
        notificar_transicion(solicitud_id, "aprobado_subgerente", usuario_nombre)
        return {"success": True, "mensaje": "Aprobado por subgerente técnico. Enviado para firma legal."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def firmar_legal(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "aprobado_legal", "AND estado = 'aprobado_subgerente'", conn=conn):
            raise ValueError("La solicitud no está en estado 'aprobado_subgerente'")
        analisis_repo.insertar_historial(solicitud_id, "aprobado_legal", usuario_rol, usuario_nombre, conn=conn)

        items_creados = _crear_items_presupuesto(solicitud_id, conn)

        conn.commit()
        notificar_transicion(solicitud_id, "aprobado_legal", usuario_nombre)
        msg = "APU aprobado y firmado legalmente. Incorporado al banco de APUs."
        if items_creados:
            msg += f" {items_creados} ítem(s) enviado(s) al presupuesto del proyecto."
        return {"success": True, "mensaje": msg, "items_creados": items_creados}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _crear_items_presupuesto(solicitud_id: int, conn) -> int:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        return 0

    # Modo 'solo insumos': es una comparación de precios entre proveedores, NO un APU.
    # No se incorpora nada al presupuesto (al proyecto solo se agregan ítems con su APU).
    if (solicitud.get("tipo_comparacion") or "apu") == "insumos":
        log.info("Solicitud %d en modo 'insumos' — no se crean ítems en el proyecto", solicitud_id)
        return 0

    analisis_data = solicitud.get("analisis") or {}
    items_analizados = analisis_data.get("items_analizados") or []

    proyecto_id = solicitud.get("proyecto_id")
    if not proyecto_id:
        log.warning("Solicitud %d sin proyecto_id — no se crearon items en presupuesto", solicitud_id)
        return 0

    creados = 0
    total_agregado = 0.0
    items_vistos = set()
    for item in items_analizados:
        codigo = (item.get("item") or "").strip()
        descripcion = (item.get("descripcion") or "").strip()
        if not codigo or not descripcion:
            continue
        if codigo in items_vistos:
            continue
        items_vistos.add(codigo)
        unidad = (item.get("unidad") or "").strip()
        precio = float(item.get("precio_ofertado") or 0)
        try:
            analisis_repo.crear_item_proyecto(
                solicitud_id, proyecto_id, codigo, descripcion,
                unidad, precio, conn=conn,
            )
            creados += 1
            total_agregado += precio
        except Exception:
            log.exception("Error creando item_proyecto para %s", codigo)

    if creados > 0:
        with conn.cursor() as cursor:
            cursor.execute(
                """UPDATE proyectos
                   SET presupuesto_total = COALESCE(presupuesto_total, 0) + %s
                   WHERE id = %s""",
                (total_agregado, proyecto_id),
            )
        log.info("Proyecto %d: presupuesto_total incrementado en %.2f", proyecto_id, total_agregado)
    return creados


def get_aprendizaje_rechazos(limit: int = 20) -> list:
    return analisis_repo.get_aprendizaje_rechazos(limit)


def eliminar_solicitud(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") in ("aprobado_legal",):
        raise ValueError("No se puede eliminar una solicitud ya firmada legalmente")
    analisis_repo.eliminar_solicitud(solicitud_id)
    return {"success": True, "mensaje": f"Solicitud #{solicitud_id} eliminada correctamente."}


def eliminar_solicitudes_lote(solicitud_ids: list[int]) -> dict:
    if not solicitud_ids:
        return {"success": True, "eliminadas": 0, "mensaje": "No se proporcionaron IDs para eliminar."}

    # Filtrar que los IDs sean enteros válidos
    ids_limpios = [int(sid) for sid in solicitud_ids if str(sid).isdigit() and int(sid) > 0]
    if not ids_limpios:
        raise ValueError("Lista de IDs inválida")

    afectadas = analisis_repo.eliminar_solicitudes_lote(ids_limpios)
    return {
        "success": True,
        "eliminadas": afectadas,
        "mensaje": f"Se eliminaron {afectadas} solicitud(es) correctamente.",
    }
