import logging
import json
import re
from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor

from db_config import get_db_connection, execute_query
from apu_extractor.ai_provider import generate_text as ai_generate

log = logging.getLogger("mapus.backend.chat")
router = APIRouter()

# ── Gemini helper ────────────────────────────────────────────────────
def gemini_generate(prompt: str) -> str:
    """Generate text using the configured AI provider."""
    system = (
        "Eres un asistente experto en bases de datos PostgreSQL "
        "y en análisis de precios unitarios (APU) de obras civiles."
    )
    return ai_generate(prompt, system=system, timeout=300)


# ── SQL helper (Strict Read-only validation) ─────────────────────────
_SQL_BLOCKED = re.compile(
    r"\b(drop\s|truncate\s|delete\s|insert\s|update\s|alter\s|"
    r"create\s|exec(ute)?\s|grant\s|revoke\s|copy\s|import\s)", re.IGNORECASE
)


def _validate_readonly_query(sql: str) -> bool:
    """Only allow SELECT queries; block any dangerous operations."""
    stripped = sql.strip()
    if not stripped.lower().startswith("select"):
        return False
    if _SQL_BLOCKED.search(stripped):
        return False
    return True


def ejecutar_sql(query: str):
    """Execute a SQL query and return results as dicts."""
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


# ── Conversational History helpers ───────────────────────────────────
def obtener_historial(telefono: str, limite: int = 5):
    """Return the last N conversation records in chronological order."""
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s
               ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows))
    except Exception as e:
        log.error("Error retrieving history for %s: %s", telefono, e)
        return []


def guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    """Save a conversation turn into the history table."""
    try:
        execute_query(
            """INSERT INTO historial_conversaciones
               (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
        log.info("Conversation stored for %s", telefono)
    except Exception as e:
        log.error("Failed to store conversation for %s: %s", telefono, e)


# ── Endpoint ─────────────────────────────────────────────────────────
@router.post("/chat-assistant")
async def chat_assistant(payload: dict):
    message = (payload.get("message") or "").strip()
    telefono = (payload.get("telefono") or "web-user").strip()
    nombre = (payload.get("nombre") or "Usuario Web").strip()

    if not message:
        return {"reply": "Escribe una pregunta sobre tus APUs."}

    log.info("Chat query from %s: %s", telefono, message[:120])

    try:
        # 1. History context
        historial = obtener_historial(telefono, limite=5)
        ctx = ""
        if historial:
            ctx = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
            for i, c in enumerate(historial, 1):
                ctx += f"Usuario: {c['mensaje_usuario']}\n"
                if c.get("sql_generado"):
                    ctx += f"SQL generado: {c['sql_generado'][:100]}...\n"
            ctx += "\nUsa el contexto para entender referencias como 'el anterior', 'compara con...', etc.\n"

        # 2. Generate SQL
        prompt = f"""Actúa como un experto en PostgreSQL y APUs.

Tabla: apus
Columnas: fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad,
contratista, nombre_proyecto, numero_contrato, item, items_descripcion,
item_unidad, precio_unitario, precio_unitario_sin_aiu, codigo_insumo,
tipo_insumo, insumo_descripcion, insumo_unidad, rendimiento_insumo,
precio_unitario_apu, precio_parcial_apu, observacion, link_documento

REGLAS:
1. Siempre usa ILIKE con % para búsquedas parciales (nunca = para textos).
2. Mapea lenguaje natural: obra/nombre_proyecto, insumo/insumo_descripcion, precio/precio_unitario.
3. LIMIT 20 salvo que pida otra cantidad.
4. Solo SELECT. Sin explicaciones. Sin ```sql```.
{ctx}
Usuario: "{message}"
SQL:"""
        sql = gemini_generate(prompt)
        sql = re.sub(r"```sql|```", "", sql).strip()
        log.info("SQL generated: %s", sql[:200])

        results = []
        if not _validate_readonly_query(sql):
            reply = "Solo puedo realizar consultas de lectura."
        else:
            results = ejecutar_sql(sql)
            if not results or "error" in results[0]:
                reply = "No encontré registros en la base de datos."
            else:
                # Serialise datetimes & Decimals
                serialised = []
                for row in results:
                    r = {}
                    for k, v in row.items():
                        if isinstance(v, (datetime, date)):
                            r[k] = v.strftime("%Y-%m-%d")
                        elif hasattr(v, "__float__"):
                            r[k] = float(v) if v is not None else None
                        else:
                            r[k] = v
                    serialised.append(r)
                results = serialised

                prompt_summary = f"""Eres un ingeniero experto en APUs.
Resume los resultados de forma clara y profesional.
Saluda a {nombre}.
Resultados: {json.dumps(results[:15], ensure_ascii=False)}
Pregunta: "{message}"
"""
                reply = gemini_generate(prompt_summary)

        guardar_conversacion(telefono, message, sql if _validate_readonly_query(sql) else "", reply)
        return {"reply": reply, "sql_query": sql if _validate_readonly_query(sql) else None, "results": results}

    except Exception as e:
        log.error("Chat assistant error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
