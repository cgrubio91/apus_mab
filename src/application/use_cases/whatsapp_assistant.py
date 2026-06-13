import json
import logging
import re

from psycopg2.extras import RealDictCursor

from src.infrastructure.database.connection import get_db_connection, execute_query
from src.infrastructure.sql_validator import validate_readonly_query
from src.infrastructure.ai.provider import ai_provider

log = logging.getLogger("mapus.application.whatsapp")


def _gemini_generate(prompt: str) -> str:
    system = "Eres un asistente experto en bases de datos PostgreSQL y en análisis de precios unitarios (APU) de obras civiles."
    return ai_provider.generate_text(prompt, system=system, timeout=300)


def usuario_autorizado(telefono: str):
    try:
        rows = execute_query("SELECT * FROM usuarios WHERE telefono = %s AND activo = true", (telefono,))
        return rows[0] if rows else None
    except Exception as e:
        log.error("Error checking user %s: %s", telefono, e)
        return None


def guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    try:
        execute_query(
            """INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
    except Exception as e:
        log.error("Failed to store conversation for %s: %s", telefono, e)


def obtener_historial(telefono: str, limite: int = 5):
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows)) if rows else []
    except Exception as e:
        log.error("Error retrieving history for %s: %s", telefono, e)
        return []


def ejecutar_sql(query: str) -> list:
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception as e:
        log.error("SQL execution error: %s", e)
        return [{"error": str(e)}]
    finally:
        if conn:
            conn.close()


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

    prompt_sql = f"""Actúa como un experto en PostgreSQL y APUs.

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

REGLAS:
1. Siempre ILIKE con % (nunca = para textos).
2. Mapea lenguaje natural a columnas.
3. Si pide "precio" o "valor unitario" del ítem, usa precio_unitario.
4. Si lista ítems, usa DISTINCT ON (item, nombre_proyecto) para evitar duplicados.
5. LIMIT 20 salvo que pida otra cantidad.
6. Solo SELECT. Sin Markdown. Sin ```sql```.
7. Para desglose de insumos, usa DISTINCT ON (item, codigo_insumo) o GROUP BY para evitar duplicados del mismo insumo.
{ctx}
Usuario: "{message_body}"
SQL:"""
    sql_query = _gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
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
