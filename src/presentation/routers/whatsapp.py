import asyncio
import logging
import os

from fastapi import APIRouter, Request
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from src.application.use_cases.whatsapp_assistant import (
    usuario_autorizado,
    guardar_conversacion,
    process_message,
)

log = logging.getLogger("mapus.presentation.whatsapp")
router = APIRouter()

ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None
twilio_validator = RequestValidator(AUTH_TOKEN) if AUTH_TOKEN else None


def _send_whatsapp_message(to: str, text: str):
    if not twilio_client:
        log.warning("Twilio client not configured, skipping message to %s", to)
        return
    try:
        twilio_client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log.info("Message sent to %s (%d chars)", to, len(text))
    except Exception as e:
        log.error("Failed to send WhatsApp to %s: %s", to, e)


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

    user = usuario_autorizado(from_number)
    if not user:
        _send_whatsapp_message(from_number, "Acceso restringido. No tienes permiso para usar este asistente.")
        log.warning("Access denied to %s", from_number)
        return "UNAUTHORIZED"

    log.info("Authorised: %s (%s)", user["nombre"], user.get("rol", "?"))

    if not message_body:
        _send_whatsapp_message(from_number, f"Hola {user['nombre']}! Envíame una pregunta sobre tus APUs.")
        return "OK"

    respuesta = process_message(from_number, message_body, user)

    guardar_conversacion(from_number, message_body, "", respuesta)

    if len(respuesta) > 1500:
        partes = [respuesta[i:i+1500] for i in range(0, len(respuesta), 1500)]
        for i, parte in enumerate(partes):
            _send_whatsapp_message(from_number, parte)
            log.info("Chunk %d/%d sent (%d chars)", i + 1, len(partes), len(parte))
            await asyncio.sleep(2)
    else:
        _send_whatsapp_message(from_number, respuesta)

    return "OK"
