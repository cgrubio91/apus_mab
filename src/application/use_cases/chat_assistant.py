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

from src.infrastructure.database.connection import get_db_connection, execute_query, DBEncoder
from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.sql_validator import validate_readonly_query
from psycopg2.extras import RealDictCursor

log = logging.getLogger("mapus.application.chat")

MAX_RESULTS_FOR_SUMMARY = 15
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


def _gemini_generate(prompt: str, system: str = "") -> str:
    default_system = "Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU) y analista avanzado de PostgreSQL. Tu objetivo es responder de manera precisa, segura y profesional."
    return ai_provider.generate_text(prompt, system=system or default_system, timeout=300)


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
        historial = _obtener_historial(telefono, 4)
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
        prompt_sql = f"""
Actúa como traductor estricto de Lenguaje Natural a PostgreSQL.

TABLA DISPONIBLE:
apus

CADA FILA = un insumo individual dentro de un ítem APU.
Un mismo ítem APU (mismo item, mismo nombre_proyecto) aparece en VARIAS filas
(una por cada insumo que lo compone).

COLUMNAS CLAVE (con semántica):
- item → código del ítem APU (ej: "APU-001")
- items_descripcion → descripción del ítem APU
- item_unidad → unidad del ítem (m3, kg, gl, etc.)
- precio_unitario → precio del INSUMO (no del ítem)
- precio_unitario_apu → PRECIO UNITARIO DEL ÍTEM APU (lo que normalmente pide el usuario)
- precio_parcial_apu → precio parcial del ítem
- precio_unitario_sin_aiu → precio sin AIU
- rendimiento_insumo → rendimiento del insumo
- codigo_insumo → código del insumo
- insumo_descripcion → descripción del insumo
- tipo_insumo → tipo (Materiales, Mano de obra, Equipos, etc.)
- insumo_unidad → unidad del insumo
- fecha_aprobacion_apu, fecha_analisis_apu → fechas
- ciudad, pais, entidad, contratista, nombre_proyecto, numero_contrato → datos del proyecto
- observacion, link_documento → metadata

REGLAS ABSOLUTAS:
1. SOLO SELECT o WITH
2. SOLO tabla apus
3. Para texto usar ILIKE con %
4. Máximo LIMIT 20
5. Nunca uses markdown
6. Nunca expliques nada en la respuesta SQL
7. Si no se puede responder usando SELECT sobre apus, responde únicamente: INVALID_QUERY
8. Nunca uses SELECT * sobre la tabla real
9. Selecciona únicamente las columnas estrictamente necesarias
10. Si el usuario pide "precio del ítem" o "valor unitario", usa precio_unitario_apu
11. Si el usuario pide listar ítems, usa SELECT DISTINCT ON (item, nombre_proyecto) para evitar duplicados
12. Si el usuario refina una consulta anterior, modifica el SQL previo en lugar de generar uno nuevo

{ctx}

Pregunta:
"{message}"

SQL:
"""
        raw_sql = _gemini_generate(prompt_sql)
        sql = re.sub(r"```sql|```", "", raw_sql).strip()
        stages.append({"phase": "Generando SQL", "duration_ms": _total_seconds() - t0})

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

        _guardar_conversacion(telefono, message, sql_to_save, reply)

        result = {
            "reply": reply,
            "sql_query": validated_sql,
            "results": results if not (results and "error" in results[0]) else [],
            "stages": stages,
            "cached": False,
            "tiene_contexto": tiene_contexto,
        }

        _chat_cache.set(cache_key, result)
        return result

    except Exception:
        log.exception("Critical error in chat_assistant")
        raise
