import json
import logging

from src.application.use_cases.assistant_common import (
    ejecutar_sql,
    gemini_generate,
    guardar_conversacion,  # noqa: F401 — re-exportado para el router de WhatsApp
    normalize_sql_for_mysql as _normalize_sql_for_mysql,
    obtener_historial,
    strip_sql_markdown,
)
from src.infrastructure.database.connection import execute_query
from src.infrastructure.sql_validator import validate_readonly_query

log = logging.getLogger("mapus.application.whatsapp")

WHATSAPP_SYSTEM_PROMPT = (
    "Eres un asistente experto en bases de datos MySQL y en análisis de precios unitarios (APU) de obras civiles."
)


def _gemini_generate(prompt: str) -> str:
    return gemini_generate(prompt, system=WHATSAPP_SYSTEM_PROMPT)


def usuario_autorizado(telefono: str):
    try:
        rows = execute_query(
            "SELECT u.id, u.phone AS telefono, u.name AS nombre, u.email "
            "FROM users u WHERE u.phone = %s",
            (telefono,),
        )
        return rows[0] if rows else None
    except Exception as e:
        log.error("Error checking user %s: %s", telefono, e)
        return None


def process_message(telefono: str, message_body: str, user: dict) -> str:
    historial = obtener_historial(telefono, limite=5)
    ctx = ""
    if historial:
        ctx = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
        for i, c in enumerate(historial, 1):
            ctx += f"Usuario: {c['mensaje_usuario']}\n"
            if c.get("sql_generado"):
                ctx += f"SQL: {c['sql_generado'][:100]}...\n"
        ctx += "\nUsa el contexto para referencias.\n"

    prompt_sql = f"""Actúa como un experto en MySQL y APUs.

Tabla: apus
CADA FILA = un insumo. Un mismo ítem APU aparece en VARIAS filas.

Columnas:
- item, items_descripcion, item_unidad → datos del ÍTEM
- precio_unitario → PRECIO DEL ÍTEM APU (lo que pide el usuario). Es CONSTANTE para todas las filas de un mismo ítem.
- precio_unitario_apu → precio del INSUMO (NO del ítem). Varía por cada insumo dentro de un mismo ítem.
- precio_parcial_apu → precio parcial del insumo (rendimiento_insumo × precio_unitario_apu)
- codigo_insumo, insumo_descripcion, tipo_insumo, rendimiento_insumo → datos del INSUMO
- fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad
- contratista, nombre_proyecto, numero_contrato
- observacion, link_documento

REGLAS (MySQL 8.0):
1. Siempre LIKE con %.
2. Mapea lenguaje natural a columnas.
3. Si pide "precio" o "valor unitario" del ítem, usa precio_unitario.
4. Para listar ítems sin duplicados usa SELECT DISTINCT.
5. LIMIT 20 salvo que pida otra cantidad.
6. Solo SELECT. Sin Markdown. Sin ```sql```.
7. Para desglose de insumos usa GROUP BY.
8. Esta es MySQL 8.0. Usa LIKE, DISTINCT (sin ON), y CAST() si es necesario.
{ctx}
Usuario: "{message_body}"
SQL:"""
    sql_query = _gemini_generate(prompt_sql)
    sql_query = strip_sql_markdown(sql_query)
    sql_query = _normalize_sql_for_mysql(sql_query)
    log.info("WhatsApp SQL: %s", sql_query[:200])

    is_valid, validated_sql = validate_readonly_query(sql_query)
    if not is_valid:
        return "Solo se permiten consultas de lectura."

    sql_query = validated_sql
    resultados = ejecutar_sql(sql_query)
    if not resultados or "error" in resultados[0]:
        return "No se encontraron resultados."

    prompt_resumen = f"""Eres un ingeniero experto en APUs.
Presenta los resultados para WhatsApp de forma clara y profesional.

FORMATO:
- LISTADOS: 1., 2., 3., con datos relevantes
- COMPARACIONES: tabla con |
- AGREGACIONES: destaca el resultado
- Sin Markdown, usa MAYÚSCULAS para títulos
- Máximo 60 caracteres por línea
- Máximo 15 resultados

Usuario: {user.get('nombre', 'Usuario')}
Pregunta: "{message_body}"
Resultados: {json.dumps(resultados, ensure_ascii=False, default=str)}
"""
    return _gemini_generate(prompt_resumen)
