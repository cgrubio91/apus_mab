import logging
import json
import re
import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from db_config import get_db_connection, execute_query, DBEncoder
from apu_extractor.ai_provider import generate_text as ai_generate
from ..sql_validator import validate_readonly_query

# ==========================================================
# CONFIG
# ==========================================================

log = logging.getLogger("mapus.backend.chat")
router = APIRouter()

MAX_RESULTS_FOR_SUMMARY = 15
MAX_FIELD_LENGTH = 300


# ==========================================================
# PYDANTIC
# ==========================================================

class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        description="Pregunta del usuario sobre APUs",
        min_length=1,
        max_length=1500
    )

    telefono: str = Field(
        default="web-user",
        description="Identificador del usuario"
    )

    nombre: str = Field(
        default="Usuario Web",
        description="Nombre del usuario"
    )


# ==========================================================
# AI HELPER
# ==========================================================

def gemini_generate(prompt: str) -> str:
    system = (
        "Eres un ingeniero civil experto en "
        "Análisis de Precios Unitarios (APU) "
        "y analista avanzado de PostgreSQL. "
        "Tu objetivo es responder de manera precisa, "
        "segura y profesional."
    )

    return ai_generate(
        prompt,
        system=system,
        timeout=300
    )


# ==========================================================
# SECURITY & SANITIZATION
# ==========================================================

def sanitize_input(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sanitize_phone(phone: str) -> str:
    return re.sub(r"[^\w\-\+]", "", phone)


def truncate_large_fields(
    data: list[dict]
) -> list[dict]:

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


# ==========================================================
# DATABASE
# ==========================================================

def ejecutar_sql(query: str) -> list[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    except Exception:
        log.exception("SQL execution error")
        return [{"error": "Error interno en la ejecución de la consulta SQL"}]


# ==========================================================
# HISTORY
# ==========================================================

def obtener_historial(
    telefono: str,
    limite: int = 5
) -> list[dict]:

    try:
        rows = execute_query(
            """
            SELECT
                mensaje_usuario,
                sql_generado,
                respuesta_bot,
                timestamp
            FROM historial_conversaciones
            WHERE telefono = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (telefono, limite),
        )
        return list(reversed(rows)) if rows else []
    except Exception:
        log.exception("Error retrieving history for %s", telefono)
        return []


def guardar_conversacion(
    telefono: str,
    mensaje: str,
    sql_: str,
    respuesta: str
):
    try:
        execute_query(
            """
            INSERT INTO historial_conversaciones
            (
                telefono,
                mensaje_usuario,
                sql_generado,
                respuesta_bot
            )
            VALUES (%s, %s, %s, %s)
            """,
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
    except Exception:
        log.exception("Failed to store conversation for %s", telefono)


# ==========================================================
# ENDPOINT
# ==========================================================

@router.post("/chat-assistant")
async def chat_assistant(
    payload: ChatRequest
) -> dict:
    message = sanitize_input(payload.message)
    telefono = sanitize_phone(payload.telefono.strip())
    nombre = sanitize_input(payload.nombre)

    log.info("Chat query from %s: %s", telefono, message[:120])

    try:
        # ==================================================
        # 1. HISTORY CONTEXT
        # ==================================================
        historial = await asyncio.to_thread(obtener_historial, telefono, 4)
        ctx = ""

        if historial:
            ctx += "\nCONTEXTO RECIENTE:\n"
            for c in historial:
                ctx += f"Usuario: {c['mensaje_usuario']}\n"
                if c.get("sql_generado"):
                    ctx += f"SQL previo: {c['sql_generado']}\n"
            ctx += "FIN CONTEXTO\n"

        # ==================================================
        # 2. SQL GENERATION
        # ==================================================
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

        raw_sql = await asyncio.to_thread(gemini_generate, prompt_sql)
        sql = re.sub(r"```sql|```", "", raw_sql).strip()

        if sql.strip().upper() == "INVALID_QUERY":
            reply = "No puedo responder esa solicitud usando la base de APUs."
            await asyncio.to_thread(guardar_conversacion, telefono, message, "", reply)
            return {
                "reply": reply,
                "sql_query": None,
                "results": []
            }

        # ==================================================
        # 3. SQL VALIDATION
        # ==================================================
        is_valid, validated_sql = validate_readonly_query(sql)

        if not is_valid:
            log.warning("Blocked SQL: %s", sql)
            reply = "Solo puedo realizar consultas de lectura sobre APUs."
            await asyncio.to_thread(guardar_conversacion, telefono, message, "", reply)
            return {
                "reply": reply,
                "sql_query": None,
                "results": []
            }

        log.info("Executing SQL: %s", validated_sql)
        results = await asyncio.to_thread(ejecutar_sql, validated_sql)

        # ==================================================
        # 4. ERROR HANDLING & SERIALIZATION
        # ==================================================
        sql_to_save = validated_sql

        if not results:
            reply = f"Hola {nombre}, no encontré resultados para tu consulta."
        elif isinstance(results, list) and "error" in results[0]:
            reply = "Hubo un problema técnico consultando la base."
            sql_to_save = ""
        else:
            safe_results = truncate_large_fields(results[:MAX_RESULTS_FOR_SUMMARY])
            json_data = json.dumps(safe_results, cls=DBTypeEncoder, ensure_ascii=False)

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
            reply = await asyncio.to_thread(gemini_generate, prompt_summary)

        # ==================================================
        # 5. SAVE HISTORY
        # ==================================================
        await asyncio.to_thread(guardar_conversacion, telefono, message, sql_to_save, reply)

        return {
            "reply": reply,
            "sql_query": validated_sql,
            "results": results if not (results and "error" in results[0]) else []
        }

    except Exception:
        log.exception("Critical error in chat_assistant")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error interno procesando la solicitud."
        )