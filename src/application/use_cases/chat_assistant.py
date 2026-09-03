"""
Application: Chat Assistant Use Case
Natural language → SQL → Results → Summary pipeline.
Features: semantic cache, multi-turn refinement, stage tracking, unified response.
"""

import json
import logging
import re
import time
import hashlib
from collections import OrderedDict

from src.application.use_cases.assistant_common import (
    build_schema_prompt,
    ejecutar_sql as _ejecutar_sql,
    gemini_generate,
    guardar_conversacion as _guardar_conversacion,
    normalize_sql_for_mysql as _normalize_sql_for_mysql,
    obtener_historial,
    strip_sql_markdown,
)
from src.infrastructure.database.connection import DBEncoder
from src.infrastructure.sql_validator import validate_readonly_query

log = logging.getLogger("mapus.application.chat")

MAX_RESULTS_FOR_SUMMARY = 40
MAX_FIELD_LENGTH = 300
CACHE_TTL = 300  # 5 minutes
CACHE_MAX_ENTRIES = 500


class ChatCache:
    def __init__(self, ttl: int = CACHE_TTL, max_entries: int = CACHE_MAX_ENTRIES):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._ttl = ttl
        self._max_entries = max_entries

    def get(self, key: str) -> dict | None:
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < self._ttl:
            return entry["data"]
        if key in self._cache:
            del self._cache[key]
        return None

    def set(self, key: str, data: dict):
        self._cache[key] = {"ts": time.time(), "data": data}
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)


_chat_cache = ChatCache()


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


CHAT_SYSTEM_PROMPT = (
    "Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU) y analista avanzado de MySQL. "
    "Tu objetivo es responder de manera precisa, segura y profesional."
)


def _gemini_generate(prompt: str, system: str = "") -> str:
    return gemini_generate(prompt, system=system or CHAT_SYSTEM_PROMPT)


def _total_seconds() -> int:
    return int(time.time() * 1000)


def _cache_key(message: str, telefono: str, historial: list) -> str:
    ctx = "|".join(
        f"{h['mensaje_usuario']}:{h.get('sql_generado', '')}" for h in historial[-2:]
    )
    raw = f"{telefono}:{ctx}:{message.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def process_chat_message(message: str, telefono: str, nombre: str) -> dict:
    message = _sanitize_input(message)
    telefono = _sanitize_phone(telefono.strip())
    nombre = _sanitize_input(nombre)
    stages: list[dict] = []

    log.info("Chat query from %s: %s", telefono, message[:120])

    try:
        historial = obtener_historial(telefono, 4)
        tiene_contexto = bool(historial)

        cache_key = _cache_key(message, telefono, historial)
        cached = _chat_cache.get(cache_key)
        if cached:
            log.info("Cache hit for: %s", message[:60])
            return cached

        ctx = ""
        if historial:
            ctx += "\nCONTEXTO DE CONVERSACIÓN PREVIA (refina o continúa según corresponda):\n"
            for c in historial:
                ctx += f"Usuario: {c['mensaje_usuario']}\n"
                if c.get("sql_generado"):
                    ctx += f"SQL previo: {c['sql_generado'][:200]}\n"
                if c.get("respuesta_bot"):
                    ctx += f"Respuesta anterior: {c['respuesta_bot'][:300]}\n"
            ctx += "\nINSTRUCCIÓN: Si el usuario pide refinar/modificar la consulta anterior, usa el SQL previo como base y ajústalo.\n"
            ctx += "FIN CONTEXTO\n"

        # ── Stage 1: SQL generation ──
        t0 = _total_seconds()
        schema_info = build_schema_prompt()
        prompt_sql = f"""Actúa como traductor estricto de Lenguaje Natural a MySQL 8.0.

{schema_info}

{ctx}

Pregunta:
"{message}"

SQL:
"""
        raw_sql = _gemini_generate(prompt_sql)
        sql = strip_sql_markdown(raw_sql)
        stages.append({"phase": "Generando SQL", "duration_ms": _total_seconds() - t0})

        sql = _normalize_sql_for_mysql(sql)

        if sql.strip().upper() == "INVALID_QUERY":
            reply = "No puedo responder esa solicitud usando la base de APUs."
            _guardar_conversacion(telefono, message, "", reply)
            result = {"reply": reply, "sql_query": None, "results": [], "stages": stages, "cached": False}
            return result

        # ── Stage 2: Validate ──
        t1 = _total_seconds()
        is_valid, validated_sql = validate_readonly_query(sql)
        stages.append({"phase": "Validando SQL", "duration_ms": _total_seconds() - t1})

        if not is_valid:
            log.warning("Blocked SQL: %s", sql)
            reply = "Solo puedo realizar consultas de lectura sobre APUs."
            _guardar_conversacion(telefono, message, "", reply)
            return {"reply": reply, "sql_query": None, "results": [], "stages": stages, "cached": False}

        # ── Stage 3: Execute ──
        t2 = _total_seconds()
        log.info("Executing SQL: %s", validated_sql)
        results = _ejecutar_sql(validated_sql)
        stages.append({"phase": "Consultando base de datos", "duration_ms": _total_seconds() - t2})
        sql_to_save = validated_sql

        # ── Stage 4: Generate response ──
        t3 = _total_seconds()
        if not results:
            reply = "No encontré resultados para tu consulta."
            if not tiene_contexto:
                reply = f"Hola {nombre}, no encontré resultados para tu consulta."
        elif isinstance(results, list) and "error" in results[0]:
            reply = "Hubo un problema técnico consultando la base."
            sql_to_save = ""
        else:
            safe_results = _truncate_large_fields(results[:MAX_RESULTS_FOR_SUMMARY])
            json_data = json.dumps(safe_results, cls=DBEncoder, ensure_ascii=False)

            saludo = "" if tiene_contexto else f"Dirígete al usuario como {nombre}."
            prompt_respuesta = f"""
Eres un ingeniero civil experto en APUs y presupuestos.
Responde de forma DIRECTA, sin rodeos ni presentaciones innecesarias.
{saludo}

INSTUCCIONES DE FORMATO:
- Si los datos contienen comparaciones entre proyectos/ítems/entidades, genera una tabla HTML:
  <table border="1"><tr><th>...</th></tr><tr><td>...</td></tr></table>
- Si los datos son agregaciones (promedios, totales, conteos), responde con un párrafo conciso.
- Números: formatea con separador de miles (ej: $1,234,567).
- Si hay datos duplicados, agrupa y muestra valores únicos.
- No repitas la misma información.
- Si los datos contienen un desglose de insumos por ítem (múltiples filas por ítem), PRESENTA TODOS los insumos de CADA ítem. No omitas ninguno. Agrupa por ítem y muestra cada insumo con su tipo, descripción y precio parcial.
- Si la consulta compara o cruza fuentes (por ejemplo apus vs precio_referencia_externa o índices DANE), ACLARA explícitamente qué precio es 'interno (banco aprobado)' y cuál es 'de mercado/externo' indicando su respectiva fuente (SECOP II, CYPE Colombia, Constructor Homecenter, ANI, etc.).
- Al final de tu respuesta, sugiere 2-3 preguntas de seguimiento útiles y naturales, separadas por "|". Ejemplo: "PREGUNTAS:¿Cuál es el precio unitario de cada uno?|Compara los costos entre estos dos proyectos|Muéstrame solo los insumos de tipo Equipos"
  Si no hay datos suficientes para sugerencias útiles, omite esta sección.

Pregunta del usuario:
"{message}"

SQL ejecutado:
{validated_sql}

Datos obtenidos:
{json_data}

Respuesta:
"""
            reply = _gemini_generate(prompt_respuesta)
        stages.append({"phase": "Redactando respuesta", "duration_ms": _total_seconds() - t3})

        suggested_followups = []
        preguntas_match = re.search(r"PREGUNTAS:(.+)", reply, re.DOTALL)
        if preguntas_match:
            suggested_followups = [
                q.strip() for q in preguntas_match.group(1).split("|") if q.strip()
            ]
            reply = reply[:preguntas_match.start()].strip()

        _guardar_conversacion(telefono, message, sql_to_save, reply)

        result = {
            "reply": reply,
            "sql_query": validated_sql,
            "results": results if not (results and "error" in results[0]) else [],
            "stages": stages,
            "cached": False,
            "tiene_contexto": tiene_contexto,
            "suggested_followups": suggested_followups,
        }

        _chat_cache.set(cache_key, result)
        return result

    except Exception:
        log.exception("Critical error in chat_assistant")
        raise
