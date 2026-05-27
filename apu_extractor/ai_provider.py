"""
🤖 AI Provider Module
Abstracts Gemini and Ollama as interchangeable AI backends.
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

# ── Configuration ────────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _call_gemini(payload: dict, timeout: int = 300) -> dict:
    """Send a request to Gemini API."""
    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=(30, timeout))
    resp.raise_for_status()
    return resp.json()


def _call_ollama(payload: dict, timeout: int = 300) -> dict:
    """Send a request to Ollama API."""
    url = f"{OLLAMA_HOST}/api/chat"
    resp = requests.post(url, json=payload, timeout=(30, timeout))
    resp.raise_for_status()
    return resp.json()


def generate_text(prompt: str, system: Optional[str] = None, timeout: int = 120) -> str:
    """
    Generate text using the configured AI provider.

    Args:
        prompt: The user prompt / instruction
        system: Optional system prompt (Ollama only; Gemini ignores)
        timeout: Max seconds to wait for response

    Returns:
        Generated text string
    """
    if AI_PROVIDER == "ollama":
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        try:
            data = _call_ollama(payload, timeout)
            return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            log.error("Ollama text generation failed: %s", e)
            return f"Error con Ollama: {e}"

    # Default: Gemini
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        data = _call_gemini(payload, timeout)
        candidates = data.get("candidates", [])
        if not candidates:
            log.error("Gemini returned no candidates: %s", json.dumps(data)[:500])
            return "No se pudo procesar tu solicitud con la IA."
        return candidates[0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log.error("Gemini text generation failed: %s", e)
        return f"Error con Gemini: {e}"


def _repair_json(raw: str) -> str:
    """
    Attempt to repair malformed JSON returned by the AI.
    Handles:
    - Unclosed strings at end of content
    - Trailing commas
    - Truncated JSON (missing closing brackets/braces)
    """
    raw = raw.strip()
    if not raw:
        return raw

    # Remove markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    # Fix unclosed strings: track quote state by unescaped quotes only.
    # This handles the case where truncation happens inside a string value,
    # where a simple count('"') % 2 would be even (first quote opens a field,
    # second quote opens the value string, but the closing quote is missing).
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

    # Remove trailing commas before closing brackets/braces
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    # Remove trailing commas at end of content
    raw = re.sub(r",\s*$", "", raw)

    # Close unclosed objects/arrays using a stack to preserve correct nesting order
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
    """
    Try to parse JSON content with repair fallback.
    Returns extracted insumos list or raises on failure.
    """
    try:
        parsed = json.loads(content)
        return parsed.get("insumos", [])
    except json.JSONDecodeError:
        log.warning("Initial JSON parse failed, attempting repair...")
        repaired = _repair_json(content)
        try:
            parsed = json.loads(repaired)
            log.info("JSON repair successful")
            return parsed.get("insumos", [])
        except json.JSONDecodeError as e:
            # Last resort: try to extract partial array from the content
            log.warning("JSON repair also failed, trying partial extraction: %s", e)
            extracted = _extract_partial_array(content)
            if extracted:
                return extracted
            raise


def _extract_partial_array(content: str) -> list:
    """
    Try to extract whatever partial data is available from a JSON-like response.
    Tries multiple strategies to salvage data from truncated JSON.
    """
    results = []

    # Strategy 1: repair and parse the whole thing
    try:
        repaired = _repair_json(content)
        parsed = json.loads(repaired)
        items = parsed.get("insumos", [])
        if items:
            return items
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: find complete array elements (objects between { and })
    # Works even when the outer array/object brackets are missing
    candidates = [content]

    # Try with repaired closing brackets
    open_brackets = content.count("[")
    close_brackets = content.count("]")
    open_braces = content.count("{")
    close_braces = content.count("}")

    if open_brackets > close_brackets:
        candidates.append(content + "]" * (open_brackets - close_brackets))
    if open_braces > close_braces:
        candidates.append(content + "}" * (open_braces - close_braces))

    for text in candidates:
        # Try to find and parse any complete JSON objects within the text
        for match in re.finditer(r'\{[^{}]*\}', text):
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict) and any(k in obj for k in ("codigo_insumo", "insumo_descripcion", "item", "items_descripcion")):
                    results.append(obj)
            except (json.JSONDecodeError, ValueError):
                continue

        # Try to find nested objects inside truncated arrays
        for match in re.finditer(r'\{[^{}]*\]', text):
            try:
                candidate = match.group()
                candidate = candidate.rstrip("]") + "}"
                obj = json.loads(candidate)
                if isinstance(obj, dict) and any(k in obj for k in ("codigo_insumo", "insumo_descripcion", "item", "items_descripcion")):
                    results.append(obj)
            except (json.JSONDecodeError, ValueError):
                continue

    return results


def extract_structured(prompt: str, document_text: str, schema: dict, timeout: int = 300) -> list:
    """
    Extract structured JSON data from document text using the configured AI provider.

    Args:
        prompt: System prompt describing the extraction task
        document_text: The document content to extract from
        schema: JSON schema for structured output (Gemini only; Ollama uses prompt instructions)
        timeout: Max seconds to wait

    Returns:
        List of extracted items (dicts)
    """
    max_attempts = 2

    if AI_PROVIDER == "ollama":
        full_prompt = f"""{prompt}

DOCUMENTO:
{document_text}

Responde SOLO con un objeto JSON válido que contenga una clave "insumos" con un array de objetos extraídos.
Cada objeto debe tener los mismos campos especificados en las instrucciones.
NO incluyas explicaciones ni texto adicional, solo el JSON."""
        for attempt in range(max_attempts):
            try:
                payload = {
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.1},
                    "format": "json",
                }
                data = _call_ollama(payload, timeout)
                content = data.get("message", {}).get("content", "").strip()
                result = _parse_json_safely(content)
                return result
            except Exception as e:
                log.warning("Ollama structured extraction attempt %d/%d failed: %s", attempt + 1, max_attempts, e)
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
            content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return _parse_json_safely(content)
        except Exception as e:
            log.warning("Gemini structured extraction attempt %d/%d failed: %s", attempt + 1, max_attempts, e)
            if attempt == max_attempts - 1:
                raise


def extract_from_pdf_multimodal(pdf_base64: str, filename: str, prompt: str, schema: dict, timeout: int = 600) -> list:
    """
    Extract from PDF using multimodal (image) understanding.
    Only available for Gemini; falls back to text-only for Ollama by raising an error.

    Uses a longer timeout (600s default) for PDF processing since large documents
    with dense tables can take several minutes per batch.

    Returns:
        List of extracted items
    """
    if AI_PROVIDER == "ollama":
        raise NotImplementedError(
            "Ollama does not support direct PDF processing. "
            "Extract text from the PDF locally first, then use extract_structured()."
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
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates for multimodal request")
        content = candidates[0]["content"]["parts"][0]["text"].strip()
        return _parse_json_safely(content)
    except Exception as e:
        log.error("Gemini PDF multimodal extraction failed for %s: %s", filename, e)
        raise
