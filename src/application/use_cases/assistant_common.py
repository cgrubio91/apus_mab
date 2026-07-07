"""
Application: helpers compartidos entre los asistentes NL→SQL (chat web y WhatsApp).
Centraliza normalización de SQL, ejecución segura, historial y persistencia
de conversaciones para evitar lógica duplicada.
"""

import logging
import re

from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.database.connection import execute_query, get_db_connection

log = logging.getLogger("mapus.application.assistant")


def normalize_sql_for_mysql(sql: str) -> str:
    """Convert common PostgreSQL syntax to MySQL-compatible."""
    # ILIKE → LIKE (MySQL LIKE is case-insensitive with utf8 collation)
    sql = re.sub(r'\bILIKE\b', 'LIKE', sql, flags=re.IGNORECASE)
    # DISTINCT ON (x, y) → DISTINCT (strip the ON clause)
    sql = re.sub(r'\bDISTINCT\s+ON\s*\([^)]*\)', 'DISTINCT', sql, flags=re.IGNORECASE)
    # :: type cast → nothing (MySQL doesn't support it)
    sql = re.sub(r'::\w+', '', sql)
    # TRUE/FALSE boolean → 1/0
    sql = re.sub(r'\bTRUE\b', '1', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bFALSE\b', '0', sql, flags=re.IGNORECASE)
    return sql


def gemini_generate(prompt: str, system: str, timeout: int = 300) -> str:
    return ai_provider.generate_text(prompt, system=system, timeout=timeout)


def strip_sql_markdown(raw_sql: str) -> str:
    return re.sub(r"```sql|```", "", raw_sql).strip()


def ejecutar_sql(query: str) -> list[dict]:
    """Ejecuta un SELECT ya validado. Nunca filtra el error real al cliente."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    except Exception as e:
        log.error("SQL execution error [%s]: %s", type(e).__name__, e)
        log.error("Failed SQL: %s", query[:500])
        return [{"error": f"Error interno en la ejecución de la consulta SQL: {type(e).__name__}"}]


def obtener_historial(telefono: str, limite: int = 5) -> list[dict]:
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows)) if rows else []
    except Exception:
        log.exception("Error retrieving history for %s", telefono)
        return []


def guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    try:
        execute_query(
            """INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
    except Exception:
        log.exception("Failed to store conversation for %s", telefono)
