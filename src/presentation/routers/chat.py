"""
Presentation: Chat Assistant Route
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.application.dto.requests import ChatRequest
from src.application.use_cases.chat_assistant import process_chat_message

log = logging.getLogger("mapus.presentation.chat")
router = APIRouter()


@router.post("/chat-assistant")
async def chat_assistant(payload: ChatRequest) -> dict:
    try:
        return process_chat_message(payload.message, payload.telefono, payload.nombre)
    except Exception:
        log.exception("Critical error in chat_assistant")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error interno procesando la solicitud.")
