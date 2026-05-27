"""
🤖 AI Provider Module
Abstracts Gemini and Ollama as interchangeable AI backends with resilient parsing.
"""

import json
import logging
import os
import re
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("mapus.ai")

# ── Límites de Seguridad de Infraestructura ─────────────────────────
MAX_DOC_CHARS = 500_000  # Evita token explosion / memory blowup en PDFs densos

# ── Dynamic Configuration Helpers ────────────────────────────────────
def get_ai_provider() -> str:
    return os.getenv("AI_PROVIDER", "gemini").strip().lower()

def get_ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# ── Fail-Fast Environment Validation ─────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if get_ai_provider() == "gemini" and not GEMINI_API_KEY:
    raise RuntimeError("Configuración Inválida: GEMINI_API_KEY no configurada en las variables de entorno.")


# ── Reutilización Eficiente de Conexiones (HTTP Keep-Alive) ──────────
SESSION = requests.Session()


def _call_gemini(payload: dict, timeout: int = 300) -> dict:
    """Send a request to Gemini API reusing connection pool sockets."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{get_gemini_model()}:generateContent?key={GEMINI_API_KEY}"
    resp = SESSION.post(
        url, 
        headers={"Content-Type": "application/json"}, 
        json=payload, 
        timeout=(30, timeout)
    )
    resp.raise_for_status()
    return resp.json()


def _call_ollama(payload: dict, timeout: int = 300) -> dict:
    """Send a request to Ollama API reusing connection pool sockets."""
    url = f"{get_ollama_host()}/api/chat"
    resp = SESSION.post(
        url, 
        headers={"Content-Type": "application/json"}, 
        json=payload, 
        timeout=(30, timeout)
    )
    resp.raise_for_status()
    return resp.json()


def _safe_extract_gemini_text(data: dict) -> Optional[str]:
    """CORRECCIÓN: Consolida robustamente todas las partes de la respuesta para evitar truncamiento."""
    candidates = data.get("candidates", [])
    if not candidates:
        prompt_feedback = data.get("promptFeedback", {})
        if prompt_feedback:
            log.warning("Gemini content block feedback: %s", json.dumps(prompt_feedback))
        return None
    
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        return None
        
    # Combina dinámicamente todos los fragmentos devueltos por el modelo
    return "".join(p.get("text", "") for p in parts).strip()


def generate_text(prompt: str, system: Optional[str] = None, timeout: int = 120) -> str:
    """Generate text using the configured AI provider, raising errors on failure."""
    provider = get_ai_provider()
    
    if provider == "ollama":
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": get_ollama_model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        try:
            data = _call_ollama(payload, timeout)
            return data.get("message", {}).get("content", "").strip()
        except Exception:
            # CORRECCIÓN: log.exception preserva el stack trace completo para monitoreo
            log.exception("Ollama text generation failed")
            raise

    # Default: Gemini
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    try:
        data = _call_gemini(payload, timeout)
        text = _safe_extract_gemini_text(data)
        if text is None:
            raise RuntimeError("Gemini devolvió una estructura sin fragmentos de texto válidos.")
        return text
    except Exception:
        log.exception("Gemini text generation failed")
        raise


def _repair_json(raw: str) -> str:
    """Intenta reparar estructuras JSON truncadas o corruptas devueltas por el LLM."""
    raw = raw.strip()
    if not raw:
        return raw

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    in_string = False
    escape = False
    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
    if in_string:
        raw = raw + '"'

    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    raw = re.sub(r",\s*$", "", raw)

    stack = []
    in_string = False
    escape = False
    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            stack.append('}')
        elif ch == '[':
            stack.append(']')
        elif ch == '}':
            if stack and stack[-1] == '}':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == ']':
                stack.pop()

    raw += "".join(reversed(stack))
    return raw


def _parse_json_safely(content: str) -> list:
    """Parsea JSON con fallbacks de reparación defensiva avanzada."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("insumos", [])
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        log.warning("Initial JSON parse failed, attempting repair...")
        repaired = _repair_json(content)
        try:
            parsed = json.loads(repaired)
            log.info("JSON repair successful")
            if isinstance(parsed, dict):
                return parsed.get("insumos", [])
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            log.warning("JSON repair failed, attempting partial flat extraction fallback")
            extracted = _extract_partial_array(content)
            if extracted:
                return extracted
            raise


def _extract_partial_array(content: str) -> list:
    """
    NOTA DE DISEÑO: Esta función sirve exclusivamente como último recurso para rescatar 
    estructuras planas (FLAT JSON). Puede fallar o ignorar datos en estructuras con anidamiento complejo.
    """
    results = []
    try:
        repaired = _repair_json(content)
        parsed = json.loads(repaired)
        items = parsed.get("insumos", []) if isinstance(parsed, dict) else parsed
        if items and isinstance(items, list):
            return items
    except Exception:
        pass

    candidates = [content]
    open_brackets = content.count("[")
    close_brackets = content.count("]")
    open_braces = content.count("{")
    close_braces = content.count("}")

    if open_brackets > close_brackets:
        candidates.append(content + "]" * (open_brackets - close_brackets))
    if open_braces > close_braces:
        candidates.append(content + "}" * (open_braces - close_braces))

    for text in candidates:
        for match in re.finditer(r'\{[^{}]*\}', text):
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict) and any(k in obj for k in ("codigo_insumo", "insumo_descripcion", "item", "items_descripcion")):
                    results.append(obj)
            except Exception:
                continue
    return results


def extract_structured(prompt: str, document_text: str, schema: dict, timeout: int = 300) -> list:
    """Extract structured JSON data from document text using the configured AI provider."""
    # CORRECCIÓN: Validación dura del contrato del esquema para evitar excepciones silenciosas del LLM
    if not isinstance(schema, dict):
        raise ValueError("El parámetro 'schema' debe ser obligatoriamente un diccionario válido (JSON Schema).")

    # CORRECCIÓN: Defensa perimetral contra desbordamiento de tokens/RAM por PDFs masivos
    document_text = document_text[:MAX_DOC_CHARS]
    max_attempts = 2
    provider = get_ai_provider()

    if provider == "ollama":
        full_prompt = f"""{prompt}

DOCUMENTO TRUNCADO (MÁX {MAX_DOC_CHARS} CARACTERES):
{document_text}

Responde SOLO con un objeto JSON válido que contenga una clave "insumos" con un array de objetos extraídos.
Cada objeto debe tener los mismos campos especificados en las instrucciones.
NO incluyas explicaciones ni texto adicional, solo el JSON."""
        for attempt in range(max_attempts):
            try:
                payload = {
                    "model": get_ollama_model(),
                    "messages": [{"role": "user", "content": full_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.1},
                    "format": "json",
                }
                data = _call_ollama(payload, timeout)
                content = data.get("message", {}).get("content", "").strip()
                return _parse_json_safely(content)
            except Exception:
                log.exception("Ollama structured extraction attempt %d/%d failed", attempt + 1, max_attempts)
                if attempt == max_attempts - 1:
                    raise

    # Default: Gemini
    for attempt in range(max_attempts):
        try:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"text": f"Aquí está el contenido del documento:\n\n{document_text}"},
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 0.1,
                },
            }
            data = _call_gemini(payload, timeout)
            content = _safe_extract_gemini_text(data)
            if content is None:
                raise RuntimeError("Gemini devolvió una estructura vacía o fue bloqueada por filtros de seguridad.")
            return _parse_json_safely(content)
        except Exception:
            log.exception("Gemini structured extraction attempt %d/%d failed", attempt + 1, max_attempts)
            if attempt == max_attempts - 1:
                raise
    return []


def extract_from_pdf_multimodal(pdf_base64: str, filename: str, prompt: str, schema: dict, timeout: int = 600) -> list:
    """Extract from PDF using multimodal (image) understanding (Gemini Only)."""
    if not isinstance(schema, dict):
        raise ValueError("El parámetro 'schema' debe ser obligatoriamente un diccionario válido (JSON Schema).")

    if get_ai_provider() == "ollama":
        raise NotImplementedError(
            "Ollama no admite procesamiento multimodal nativo de archivos PDF completos en este flujo. "
            "Extraiga el texto del PDF localmente y use la función extract_structured()."
        )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "application/pdf", "data": pdf_base64}},
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.1,
        },
    }
    try:
        data = _call_gemini(payload, timeout)
        content = _safe_extract_gemini_text(data)
        if content is None:
            raise RuntimeError("Gemini no devolvió candidatos válidos para la extracción multimodal del PDF.")
        return _parse_json_safely(content)
    except Exception:
        log.exception("Gemini PDF multimodal extraction failed for %s", filename)
        raise