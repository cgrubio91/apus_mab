import logging
import json
import re
import asyncio

from datetime import datetime, date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from db_config import get_db_connection, execute_query
from apu_extractor.ai_provider import generate_text as ai_generate

# ==========================================================
# CONFIG
# ==========================================================

log = logging.getLogger("mapus.backend.chat")
router = APIRouter()

MAX_RESULTS_FOR_SUMMARY = 15
MAX_FIELD_LENGTH = 300
MAX_LIMIT_ALLOWED = 20

_ALLOWED_TABLES = {"apus"}

# Soporta consultas avanzadas con CTEs (WITH ...)
_ALLOWED_SQL = re.compile(
    r"^\s*(select|with)\b",
    re.IGNORECASE
)

# CORRECCIÓN: Keywords estrictas con límites de palabra (\b) mediante VERBOSE.
# Se eliminó 'comment' para evitar falsos positivos con la palabra 'comentario'.
_DANGEROUS_SQL = re.compile(
    r"""
    \b(
    drop|truncate|delete|insert|update|
    alter|create|execute|exec|
    grant|revoke|copy|
    vacuum|analyze|merge
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)


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
# JSON ENCODER
# ==========================================================

class DBTypeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.strftime("%Y-%m-%d")

        if isinstance(obj, Decimal):
            return float(obj)

        return super().default(obj)


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


def validate_readonly_query(
    sql: str
) -> tuple[bool, str]:

    if not sql:
        return False, "SQL vacío"

    sql = sql.strip()

    # No multi-statements
    if ";" in sql:
        return False, "No se permiten múltiples queries"

    # Debe iniciar por SELECT o WITH
    if not _ALLOWED_SQL.match(sql):
        return False, "Solo se permiten consultas SELECT o WITH"

    # Bloquear keywords peligrosas aisladas por límites de palabra
    if _DANGEROUS_SQL.search(sql):
        return False, "SQL peligroso detectado"

    # CORRECCIÓN: Detectar múltiples nombres de CTEs soportando encadenamiento por comas
    cte_names = set(
        match.lower()
        for match in re.findall(
            r"(?:with|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as",
            sql,
            re.IGNORECASE
        )
    )

    # Detectar todas las tablas o alias usados en las cláusulas FROM y JOIN
    tables = re.findall(
        r"(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.IGNORECASE
    )

    # Validar tablas físicas permitidas o CTEs internos válidos
    for table in tables:
        table_lower = table.lower()
        if (
            table_lower not in _ALLOWED_TABLES
            and table_lower not in cte_names
        ):
            return False, f"Tabla no autorizada: {table}"

    # CORRECCIÓN: Permite SELECT * sobre CTEs intermedios pero lo bloquea estrictamente sobre la tabla real
    select_star_matches = re.findall(
        r"select\s+\*\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.IGNORECASE
    )

    for table in select_star_matches:
        if table.lower() in _ALLOWED_TABLES:
            return False, "SELECT * no permitido sobre tablas reales"

    # Forzar LIMIT de seguridad si pasó los filtros previos
    has_limit = re.search(
        r"\blimit\s+(\d+)",
        sql,
        re.IGNORECASE
    )

    if has_limit:
        limit_value = int(has_limit.group(1))
        if limit_value > MAX_LIMIT_ALLOWED:
            sql = re.sub(
                r"\blimit\s+\d+",
                f"LIMIT {MAX_LIMIT_ALLOWED}",
                sql,
                flags=re.IGNORECASE
            )
    else:
        sql += f" LIMIT {MAX_LIMIT_ALLOWED}"

    return True, sql


# ==========================================================
# DATABASE
# ==========================================================

def ejecutar_sql(query: str) -> list[dict]:
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception:
        log.exception("SQL execution error")
        return [{"error": "Error interno en la ejecución de la consulta SQL"}]
    finally:
        if conn:
            conn.close()


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
):
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