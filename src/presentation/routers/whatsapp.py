"""
Presentation: WhatsApp Webhook Route
Twilio integration for WhatsApp-based APU queries.
"""

import asyncio
import json
import logging
import os
import re

from fastapi import APIRouter, HTTPException, Request
from psycopg2.extras import RealDictCursor
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from src.infrastructure.database.connection import get_db_connection, execute_query
from src.infrastructure.sql_validator import validate_readonly_query
from src.infrastructure.ai.provider import ai_provider

log = logging.getLogger("mapus.presentation.whatsapp")
router = APIRouter()

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None
twilio_validator = RequestValidator(AUTH_TOKEN) if AUTH_TOKEN else None


def _gemini_generate(prompt: str) -> str:
    system = "Eres un asistente experto en bases de datos PostgreSQL y en análisis de precios unitarios (APU) de obras civiles."
    return ai_provider.generate_text(prompt, system=system, timeout=300)


def _send_whatsapp_message(to: str, text: str):
    if not twilio_client:
        log.warning("Twilio client not configured, skipping message to %s", to)
        return
    try:
        twilio_client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log.info("Message sent to %s (%d chars)", to, len(text))
    except Exception as e:
        log.error("Failed to send WhatsApp to %s: %s", to, e)


def _usuario_autorizado(telefono: str):
    try:
        rows = execute_query("SELECT * FROM usuarios WHERE telefono = %s AND activo = true", (telefono,))
        return rows[0] if rows else None
    except Exception as e:
        log.error("Error checking user %s: %s", telefono, e)
        return None


def _guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    try:
        execute_query(
            """INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
        log.info("Conversation stored for %s", telefono)
    except Exception as e:
        log.error("Failed to store conversation for %s: %s", telefono, e)


def _obtener_historial(telefono: str, limite: int = 5):
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows))
    except Exception as e:
        log.error("Error retrieving history for %s: %s", telefono, e)
        return []


def _ejecutar_sql(query: str):
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


@router.post("/whatsapp_webhook")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
    except Exception as e:
        log.error("Failed to parse webhook form: %s", e)
        return "OK"

    from_number = (form.get("From") or "").strip()
    message_body = (form.get("Body") or "").strip()

    if twilio_validator:
        signature = request.headers.get("X-Twilio-Signature", "")
        params = {k: v for k, v in form.items()}
        url = str(request.url).replace("http://", "https://")
        if not twilio_validator.validate(url, params, signature):
            log.warning("Invalid Twilio signature from %s", from_number)
            return "UNAUTHORIZED"

    log.info("WhatsApp from %s: %s", from_number, message_body[:120])

    user = _usuario_autorizado(from_number)
    if not user:
        _send_whatsapp_message(from_number, "Acceso restringido. No tienes permiso para usar este asistente.")
        log.warning("Access denied to %s", from_number)
        return "UNAUTHORIZED"

    log.info("Authorised: %s (%s)", user["nombre"], user.get("rol", "?"))

    if not message_body:
        _send_whatsapp_message(from_number, f"Hola {user['nombre']}! Envíame una pregunta sobre tus APUs.")
        return "OK"

    historial = _obtener_historial(from_number, limite=5)
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
Columnas: fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad,
contratista, nombre_proyecto, numero_contrato, item, items_descripcion,
item_unidad, precio_unitario, precio_unitario_sin_aiu, codigo_insumo,
tipo_insumo, insumo_descripcion, insumo_unidad, rendimiento_insumo,
precio_unitario_apu, precio_parcial_apu, observacion, link_documento

REGLAS:
1. Siempre ILIKE con % (nunca = para textos).
2. Mapea lenguaje natural a columnas.
3. LIMIT 20 salvo que pida otra cantidad.
4. Solo SELECT. Sin Markdown. Sin ```sql```.
{ctx}
Usuario: "{message_body}"
SQL:"""
    sql_query = _gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
    log.info("WhatsApp SQL: %s", sql_query[:200])

    is_valid, validated_sql = validate_readonly_query(sql_query)
    if not is_valid:
        respuesta = "Solo se permiten consultas de lectura."
    else:
        sql_query = validated_sql
        resultados = _ejecutar_sql(sql_query)
        if not resultados or "error" in resultados[0]:
            respuesta = "No se encontraron resultados."
        else:
            prompt_resumen = f"""Eres un ingeniero experto en APUs.
Presenta los resultados para WhatsApp de forma clara y profesional.

FORMATO:
- LISTADOS: 1., 2., 3., con datos relevantes
- COMPARACIONES: tabla con |
- AGREGACIONES: destaca el resultado
- Sin Markdown, usa MAYÚSCULAS para títulos
- Máximo 60 caracteres por línea
- Máximo 15 resultados

Usuario: {user['nombre']}
Pregunta: "{message_body}"
Resultados: {json.dumps(resultados, ensure_ascii=False, default=str)}
"""
            respuesta = _gemini_generate(prompt_resumen)

    _guardar_conversacion(from_number, message_body, sql_query if is_valid else "", respuesta)

    if len(respuesta) > 1500:
        partes = [respuesta[i:i+1500] for i in range(0, len(respuesta), 1500)]
        for i, parte in enumerate(partes):
            _send_whatsapp_message(from_number, parte)
            log.info("Chunk %d/%d sent (%d chars)", i + 1, len(partes), len(parte))
            await asyncio.sleep(2)
    else:
        _send_whatsapp_message(from_number, respuesta)

    return "OK"
