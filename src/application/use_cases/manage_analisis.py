"""
Application: Manage Análisis APU Use Case
Approval workflow orchestration: create, analyze, pre-approve, reject, approve.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from src.application.use_cases.notificaciones import notificar_transicion
from src.infrastructure.database.repositories.analisis_repository import analisis_repo
from src.infrastructure.ai.provider import ai_provider

log = logging.getLogger("mapus.application.analisis")

ESTADOS = [
    "pendiente_analisis",
    "analizado",
    "preaprobado",
    "rechazado",
    "nuevas_cotizaciones",
    "aprobado_subgerente",
    "aprobado_legal",
]


def crear_solicitud(grupos_insumos: list[dict]) -> int:
    return analisis_repo.crear_solicitud(grupos_insumos)


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

    items_analizados = []
    for ins in insumos:
        resultado = _analizar_item_con_banco(ins)
        items_analizados.append(resultado)

    comparacion_grupos = analisis_repo._analizar_mejor_grupo(insumos, items_analizados)
    resumen, recomendacion = _generar_resumen_ia(insumos, items_analizados, comparacion_grupos)

    analisis_json = json.dumps({"items": items_analizados, "comparacion_grupos": comparacion_grupos}, default=str)

    analisis_repo.guardar_analisis(solicitud_id, analisis_json, resumen, recomendacion)
    analisis_repo.actualizar_estado(solicitud_id, "analizado")
    notificar_transicion(solicitud_id, "analizado")

    return {
        "solicitud_id": solicitud_id,
        "items_analizados": items_analizados,
        "resumen": resumen,
        "recomendacion": recomendacion,
    }


def _analizar_item_con_banco(ins: dict) -> dict:
    descripcion = ins.get("items_descripcion", "")
    precio_ofertado = float(ins.get("precio_unitario") or 0)

    resultado = {
        "item": ins.get("item", ""),
        "descripcion": descripcion,
        "unidad": ins.get("item_unidad", ""),
        "precio_ofertado": precio_ofertado,
        "mejor_precio_banco": None,
        "diferencia_precio": None,
        "existe_en_banco": False,
        "item_banco_encontrado": None,
        "estructura_insumos_coincide": None,
        "rendimiento_coincide": None,
        "observaciones": "Sin descripción para comparar" if not descripcion else "",
        "recomendacion": "pendiente",
        "grupo_cotizacion": ins.get("grupo_cotizacion", 1),
    }

    if not descripcion:
        return resultado

    banco_records = analisis_repo.buscar_en_banco(descripcion)
    resultado["existe_en_banco"] = len(banco_records) > 0

    if banco_records:
        mejor_precio = min(
            float(r.get("precio_unitario") or float("inf"))
            for r in banco_records
            if r.get("precio_unitario") is not None
        )
        resultado["mejor_precio_banco"] = mejor_precio
        resultado["diferencia_precio"] = round(precio_ofertado - mejor_precio, 2)
        resultado["item_banco_encontrado"] = banco_records[0].get("item", "")

    resultado = _analisis_con_ia(ins, banco_records, resultado)
    return resultado


def _contexto_aprendizaje_rechazos(limit: int = 10) -> str:
    """Motivos de rechazos históricos para que la IA aplique criterios que los
    revisores humanos ya usaron. Devuelve cadena vacía si no hay datos."""
    try:
        rechazos = analisis_repo.get_aprendizaje_rechazos(limit)
    except Exception:
        log.exception("No se pudo consultar aprendizaje_rechazos")
        return ""
    if not rechazos:
        return ""
    lineas = "\n".join(
        f"- {r.get('motivo_rechazo', '')}" for r in rechazos if r.get("motivo_rechazo")
    )
    if not lineas:
        return ""
    return f"""
CRITERIOS APRENDIDOS DE RECHAZOS ANTERIORES (los revisores humanos rechazaron cotizaciones por estos motivos;
tenlos en cuenta al evaluar y menciona en observaciones si alguno aplica):
{lineas}
"""


def _analisis_con_ia(insumo: dict, banco_records: list, resultado: dict) -> dict:
    tiene_banco = len(banco_records) > 0
    prompt_banco = json.dumps(banco_records, default=str, indent=2) if tiene_banco else "NO HAY registros similares en el banco de APUs."
    contexto_rechazos = _contexto_aprendizaje_rechazos()

    prompt = f"""Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU).

ÍTEM COTIZADO:
- Código: {insumo.get('item', 'N/A')}
- Descripción: {insumo.get('items_descripcion', 'N/A')}
- Unidad: {insumo.get('item_unidad', 'N/A')}
- Precio Unitario: ${insumo.get('precio_unitario', 'N/A')}
- Código Insumo: {insumo.get('codigo_insumo', 'N/A')}
- Descripción Insumo: {insumo.get('insumo_descripcion', 'N/A')}
- Unidad Insumo: {insumo.get('insumo_unidad', 'N/A')}
- Rendimiento: {insumo.get('rendimiento_insumo', 'N/A')}
- Tipo Insumo: {insumo.get('tipo_insumo', 'N/A')}

DATOS DEL BANCO DE APUs:
{prompt_banco}
{contexto_rechazos}
INSTRUCCIONES:
- Si HAY datos en el banco, compáralos (estructura de insumos, rendimientos, precios).
- Si NO HAY datos similares en el banco, evalúa el precio del ítem según tu criterio profesional.

Analiza y responde SOLO con un JSON válido con estos campos:
- estructura_insumos_coincide: true/false (si hay banco; null si no hay)
- rendimiento_coincide: true/false (si hay banco; null si no hay)
- observaciones: string con explicación breve
- recomendacion: "aprobar" o "rechazar" o "revisar"

NO incluyas texto adicional, solo el JSON."""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        respuesta = respuesta.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("\n", 1)[-1]
            respuesta = respuesta.rsplit("```", 1)[0]
        analisis = json.loads(respuesta)
        resultado["estructura_insumos_coincide"] = analisis.get("estructura_insumos_coincide")
        resultado["rendimiento_coincide"] = analisis.get("rendimiento_coincide")
        if analisis.get("observaciones"):
            resultado["observaciones"] = analisis["observaciones"]
        resultado["recomendacion"] = analisis.get("recomendacion", "revisar")
    except Exception as e:
        log.exception("Error en análisis IA para ítem %s: %s", insumo.get("item"), e)
        resultado["observaciones"] = "No se pudo completar el análisis automático"
        resultado["recomendacion"] = "revisar"

    return resultado


def _generar_resumen_ia(insumos: list, items_analizados: list, comparacion_grupos: dict = None) -> tuple:
    total_items = len(items_analizados)
    recomendaciones = [i.get("recomendacion", "") for i in items_analizados]
    aprobar = sum(1 for r in recomendaciones if r == "aprobar")
    rechazar = sum(1 for r in recomendaciones if r == "rechazar")
    revisar = sum(1 for r in recomendaciones if r == "revisar")
    items_con_banco = sum(1 for i in items_analizados if i.get("existe_en_banco"))
    items_sin_banco = total_items - items_con_banco

    grupo_info = ""
    if comparacion_grupos and comparacion_grupos.get("total_grupos", 0) > 1:
        grupos = comparacion_grupos.get("grupos", {})
        mejor = comparacion_grupos.get("mejor_grupo")
        grupo_info = "\nCOMPARACIÓN ENTRE COTIZACIONES:\n"
        for g, info in grupos.items():
            marca = " ← MEJOR OPCIÓN" if g == mejor else ""
            grupo_info += f"Cotización {g} ({info.get('archivo', '')}): ${info.get('total', 0):,.0f} total, ${info.get('promedio', 0):,.0f} promedio/ítem{marca}\n"
        grupo_info += f"\nLa cotización con mejor relación precio es: Cotización {mejor}\n"

    prompt = f"""Eres un ingeniero civil experto en APUs.
Genera un resumen ejecutivo del siguiente análisis de cotizaciones APU.

Total de ítems analizados: {total_items}
Aprobados por IA: {aprobar}
Rechazados por IA: {rechazar}
Para revisión manual: {revisar}
Ítems con datos en banco de APUs: {items_con_banco}
Ítems SIN datos en banco de APUs: {items_sin_banco}
{grupo_info}

Detalle del análisis:
{json.dumps(items_analizados, default=str, indent=2)}

Responde SOLO con un JSON:
{{"resumen": "texto del resumen", "recomendacion": "aprobar|rechazar|revisar"}}"""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        import re
        text = respuesta.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        try:
            resultado = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                resultado = json.loads(text[brace_start:brace_end + 1])
            else:
                raise
        if resultado.get("resumen") and resultado.get("recomendacion"):
            return resultado["resumen"], resultado["recomendacion"]
    except Exception as e:
        log.warning("Error generando resumen IA: %s", e)

    return f"Se analizaron {total_items} ítems ({items_con_banco} con datos en banco, {items_sin_banco} sin datos). {aprobar} aprobados, {rechazar} rechazados, {revisar} en revisión.", "revisar"


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
        conn.commit()
        notificar_transicion(solicitud_id, "aprobado_legal", usuario_nombre)
        return {"success": True, "mensaje": "APU aprobado y firmado legalmente. Incorporado al banco de APUs."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_aprendizaje_rechazos(limit: int = 20) -> list:
    return analisis_repo.get_aprendizaje_rechazos(limit)
