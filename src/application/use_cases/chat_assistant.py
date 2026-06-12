"""
Application: Chat Assistant Use Case
Natural language → SQL → Results → Summary pipeline.
"""

import json
import logging
import re
import asyncio

from src.infrastructure.database.connection import get_db_connection, execute_query, DBEncoder
from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.sql_validator import validate_readonly_query
from psycopg2.extras import RealDictCursor

log = logging.getLogger("mapus.application.chat")

MAX_RESULTS_FOR_SUMMARY = 15
MAX_FIELD_LENGTH = 300


def _sanitize_input(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_phone(phone: str) -> str:
    return re.sub(r"[^\w\-\+]", "", phone)


def _truncate_large_fields(data: list[dict]) -> list[dict]:
    cleaned = []
    for row in data:
        new_row = {}
        for key, value in row.items():
            if isinstance(value, str):
                new_row[key] = value[:MAX_FIELD_LENGTH]
            else:
                new_row[key] = value
        cleaned.append(new_row)
    return cleaned


def _gemini_generate(prompt: str) -> str:
    system = "Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU) y analista avanzado de PostgreSQL. Tu objetivo es responder de manera precisa, segura y profesional."
    return ai_provider.generate_text(prompt, system=system, timeout=300)


def _ejecutar_sql(query: str) -> list[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    except Exception:
        log.exception("SQL execution error")
        return [{"error": "Error interno en la ejecución de la consulta SQL"}]


def _obtener_historial(telefono: str, limite: int = 5) -> list[dict]:
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


def _guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    try:
        execute_query(
            """INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
    except Exception:
        log.exception("Failed to store conversation for %s", telefono)


def process_chat_message(message: str, telefono: str, nombre: str) -> dict:
    message = _sanitize_input(message)
    telefono = _sanitize_phone(telefono.strip())
    nombre = _sanitize_input(nombre)

    log.info("Chat query from %s: %s", telefono, message[:120])

    try:
        historial = _obtener_historial(telefono, 4)
        ctx = ""
        if historial:
            ctx += "\nCONTEXTO RECIENTE:\n"
            for c in historial:
                ctx += f"Usuario: {c['mensaje_usuario']}\n"
                if c.get("sql_generado"):
                    ctx += f"SQL previo: {c['sql_generado']}\n"
            ctx += "FIN CONTEXTO\n"

        prompt_sql = f"""
Actúa como traductor estricto de Lenguaje Natural a PostgreSQL.

TABLA DISPONIBLE:
apus

COLUMNAS:
- fecha_aprobacion_apu
- fecha_analisis_apu
- ciudad
- pais
- entidad
- contratista
- nombre_proyecto
- numero_contrato
- item
- items_descripcion
- item_unidad
- observacion
- link_documento
- codigo_insumo
- tipo_insumo
- insumo_descripcion
- insumo_unidad
- rendimiento_insumo
- precio_unitario
- precio_unitario_sin_aiu
- precio_unitario_apu
- precio_parcial_apu

REGLAS ABSOLUTAS:
1. SOLO SELECT o WITH
2. SOLO tabla apus
3. Para texto usar ILIKE
4. Máximo LIMIT 20
5. Nunca uses markdown
6. Nunca expliques nada
7. Si no se puede responder usando SELECT sobre apus, responde únicamente: INVALID_QUERY
8. Nunca uses SELECT * sobre la tabla real
9. Selecciona únicamente las columnas estrictamente necesarias para responder la pregunta

{ctx}

Pregunta:
"{message}"

SQL:
"""
        raw_sql = _gemini_generate(prompt_sql)
        sql = re.sub(r"```sql|```", "", raw_sql).strip()

        if sql.strip().upper() == "INVALID_QUERY":
            reply = "No puedo responder esa solicitud usando la base de APUs."
            _guardar_conversacion(telefono, message, "", reply)
            return {"reply": reply, "sql_query": None, "results": []}

        is_valid, validated_sql = validate_readonly_query(sql)
        if not is_valid:
            log.warning("Blocked SQL: %s", sql)
            reply = "Solo puedo realizar consultas de lectura sobre APUs."
            _guardar_conversacion(telefono, message, "", reply)
            return {"reply": reply, "sql_query": None, "results": []}

        log.info("Executing SQL: %s", validated_sql)
        results = _ejecutar_sql(validated_sql)
        sql_to_save = validated_sql

        if not results:
            reply = f"Hola {nombre}, no encontré resultados para tu consulta."
        elif isinstance(results, list) and "error" in results[0]:
            reply = "Hubo un problema técnico consultando la base."
            sql_to_save = ""
        else:
            safe_results = _truncate_large_fields(results[:MAX_RESULTS_FOR_SUMMARY])
            json_data = json.dumps(safe_results, cls=DBEncoder, ensure_ascii=False)

            prompt_summary = f"""
Eres un ingeniero civil experto en APUs y presupuestos.
Resume de forma clara, amigable y profesional.
Dirígete a {nombre}.

Pregunta:
"{message}"

Datos:
{json_data}

Resumen:
"""
            reply = _gemini_generate(prompt_summary)

        _guardar_conversacion(telefono, message, sql_to_save, reply)

        return {
            "reply": reply,
            "sql_query": validated_sql,
            "results": results if not (results and "error" in results[0]) else [],
        }

    except Exception:
        log.exception("Critical error in chat_assistant")
        raise
