"""
🧠 AI Extractor Module
Extracts structured APU data from documents using the configured AI provider (Gemini / Ollama).
Cleans, normalizes, and formats data using high-precision Decimal types for construction budgets.
"""

import os
import base64
import tempfile
import logging
from dotenv import load_dotenv

from apu_extractor.ai_provider import (
    extract_structured,
    extract_from_pdf_multimodal,
)
from apu_extractor.gemini_cleaners import (
    clean_numeric_value,
    format_latin_number,
    format_date,
    clean_text_field,
    normalize_ai_response,
)
from apu_extractor.gemini_prompts import get_extraction_prompt, get_response_schema
from db_schema import INSUMO_CATEGORIES

if os.getenv("ENV", "").lower() != "production":
    load_dotenv()

log = logging.getLogger("mapus.extractor")


# ==========================================================
# EXTRACTION METHODS
# ==========================================================

def extract_apus_from_text(document_text: str, filename: str = None) -> list[dict]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    raw_result = extract_structured(prompt, document_text, schema)
    return normalize_ai_response(raw_result)


def extract_apus_from_pdf_multimodal(pdf_base64: str, filename: str = None) -> list[dict]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    tmp_path = None
    
    try:
        raw_result = extract_from_pdf_multimodal(pdf_base64, filename, prompt, schema)
        return normalize_ai_response(raw_result)
    except NotImplementedError:
        log.warning("PDF multimodal not supported by current provider, extracting text first")
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
                
            from apu_extractor.pdf_parser import extract_text_from_pdf
            text = extract_text_from_pdf(tmp_path)
            if text.strip():
                raw_result = extract_structured(prompt, text, schema)
                return normalize_ai_response(raw_result)
            return []
        except Exception:
            log.exception("Safe extraction text fallback failed")
            raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def extract_apus_from_excel(excel_path: str, filename: str = None, progress_callback=None) -> list[dict]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    from apu_extractor.excel_parser import extract_text_from_excel_batched

    all_insumos = []
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()

    for i, (sheet_name, chunk_text) in enumerate(extract_text_from_excel_batched(excel_path), start=1):
        log.info("Processing batch %d from %s / %s (%d chars)", i, filename or excel_path, sheet_name, len(chunk_text))
        
        if progress_callback:
            progress_callback(i, None, f"Procesando hoja {sheet_name} (Bloque {i})")
            
        try:
            batch_result = extract_structured(prompt, chunk_text, schema)
            normalized = normalize_ai_response(batch_result)
            all_insumos.extend(normalized)
            log.info("Batch %d processed successfully -> %d insumos extracted", i, len(normalized))
        except Exception:
            log.exception("Batch execution failed for %s / %s", filename or excel_path, sheet_name)

    log.info("Extracted %d insumos from %s (batched)", len(all_insumos), filename or excel_path)
    return all_insumos


MAX_MULTIMODAL_PAGES = 30

def _get_pdf_page_count(pdf_path: str) -> int:
    """Get total page count of a PDF using pypdf."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(pdf_path)
        return len(reader.pages)
    except Exception:
        log.exception("Failed to read PDF page count dynamically for file: %s", pdf_path)
        return -1


def extract_apus_from_pdf_batched(pdf_path: str, filename: str = None, progress_callback=None) -> list[dict]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    from apu_extractor.pdf_parser import extract_text_from_pdf_batched

    all_insumos = []
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    total_pages = _get_pdf_page_count(pdf_path)

    use_multimodal = total_pages > 0 and total_pages <= MAX_MULTIMODAL_PAGES

    if use_multimodal:
        from apu_extractor.pdf_parser import split_pdf_to_base64_batches
        try:
            if progress_callback:
                progress_callback(1, None, "Preparando páginas del PDF para análisis visual...")
                
            for idx, (label, pdf_b64) in enumerate(split_pdf_to_base64_batches(pdf_path), start=1):
                log.info("Multimodal batch %s (%d b64 chars)", label, len(pdf_b64))
                if progress_callback:
                    progress_callback(idx, None, f"IA GEMINI · Analizando imágenes de {label}...")
                try:
                    batch_result = extract_from_pdf_multimodal(pdf_b64, f"{filename} ({label})", prompt, schema)
                    normalized = normalize_ai_response(batch_result)
                    all_insumos.extend(normalized)
                    log.info("Multimodal batch %s → %d insumos reales", label, len(normalized))
                except NotImplementedError:
                    log.info("Multimodal not supported for %s, switching to text", label)
                    use_multimodal = False
                    break
                except Exception as e:
                    log.exception("Multimodal batch %s execution failed: %s", label, str(e))
                    
            if use_multimodal:
                log.info("Extracted %d insumos from %s (multimodal batched)", len(all_insumos), filename or pdf_path)
                return all_insumos
        except NotImplementedError:
            log.info("Multimodal not available, using text batches")

    total_text_batches = max(1, (total_pages + 4) // 5) if total_pages > 0 else 1
    log.info("Using text-based extraction for %s (%d pages, %d batches)", filename or pdf_path, total_pages, total_text_batches)

    if progress_callback:
        progress_callback(0, total_text_batches, "Leyendo documento PDF (esto puede tardar unos minutos)...")

    text_batches_gen = extract_text_from_pdf_batched(pdf_path)
    
    for idx, (label, chunk_text) in enumerate(text_batches_gen):
        log.info("Text batch %s (%d chars)", label, len(chunk_text))
        if progress_callback:
            progress_callback(idx + 1, total_text_batches, f"IA GEMINI · Procesando texto de {label}...")
            
        try:
            batch_result = extract_structured(prompt, chunk_text, schema)
            normalized = normalize_ai_response(batch_result)
            all_insumos.extend(normalized)
            log.info("Text batch %s → %d insumos reales", label, len(normalized))
        except Exception as e:
            log.exception("Text batch %s processing failed: %s", label, str(e))

    log.info("Extracted %d insumos from %s (text batched)", len(all_insumos), filename or pdf_path)
    return all_insumos


# ==========================================================
# POST PROCESSING & ETLS
# ==========================================================

def _classify_tipo_insumo(insumos: list) -> None:
    """
    Clasifica el 'tipo_insumo' de cada insumo usando la IA en lotes,
    según las categorías: Equipos, Herramienta, Materiales, Mano de obra, Transporte, Indirectos.
    Se basa en 'insumo_descripcion' para determinar la categoría.
    """
    from apu_extractor.ai_provider import generate_text

    descriptions = []
    index_map = []
    for i, item in enumerate(insumos):
        desc = (item.get("insumo_descripcion") or "").strip()
        if desc and desc != "–":
            descriptions.append(desc)
            index_map.append(i)

    if not descriptions:
        return

    CATEGORIES = INSUMO_CATEGORIES
    BATCH_SIZE = 80

    for batch_start in range(0, len(descriptions), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(descriptions))
        batch_descs = descriptions[batch_start:batch_end]
        batch_indices = index_map[batch_start:batch_end]

        prompt = (
            f"Clasifica cada insumo de construcción en EXACTAMENTE una de estas {len(CATEGORIES)} categorías:\n"
            + "\n".join(f"{i+1}. {c}" for i, c in enumerate(CATEGORIES))
            + "\n\nResponde SOLO con un objeto JSON donde cada clave es el número de orden "
            "y el valor es la categoría asignada.\n\n"
            "Lista de insumos:\n"
        )
        for idx, desc in enumerate(batch_descs, start=1):
            prompt += f"{idx}. {desc}\n"

        prompt += (
            '\n\nEjemplo de respuesta:\n'
            '{"1": "Materiales", "2": "Mano de obra", "3": "Equipos"}\n'
            'NO agregues explicaciones, solo el JSON.'
        )

        try:
            raw = generate_text(prompt, timeout=120)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()
            import json as _json
            result = _json.loads(raw)
            for str_idx, categoria in result.items():
                i = int(str_idx) - 1
                if 0 <= i < len(batch_indices):
                    insumos[batch_indices[i]]["tipo_insumo"] = categoria.strip()
        except Exception:
            log.exception("Fallback: clasificación por IA no disponible, se usan valores originales")


def post_process_extracted_data(insumos: list, filename: str = None) -> list[dict]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    cleaned_list = []
    
    for item in insumos:
        if not isinstance(item, dict):
            log.warning("Saltando registro malformado devuelto por el LLM (No es un diccionario válido): %s", item)
            continue

        cleaned = {
            "fecha_aprobacion_apu": format_date(item.get("fecha_aprobacion_apu")),
            "fecha_analisis_apu": format_date(item.get("fecha_analisis_apu")),
            "ciudad": clean_text_field(item.get("ciudad")),
            "pais": clean_text_field(item.get("pais")),
            "entidad": clean_text_field(item.get("entidad")),
            "contratista": clean_text_field(item.get("contratista")),
            "nombre_proyecto": clean_text_field(item.get("nombre_proyecto")),
            "numero_contrato": clean_text_field(item.get("numero_contrato")),
            
            "item": clean_text_field(item.get("item")),
            "items_descripcion": clean_text_field(item.get("items_descripcion")),
            "item_unidad": clean_text_field(item.get("item_unidad")),
            
            "precio_unitario": clean_numeric_value(item.get("precio_unitario")),
            "precio_unitario_sin_aiu": clean_numeric_value(item.get("precio_unitario_sin_aiu")),
            
            "codigo_insumo": clean_text_field(item.get("codigo_insumo")),
            "tipo_insumo": clean_text_field(item.get("tipo_insumo")),
            "insumo_descripcion": clean_text_field(item.get("insumo_descripcion")),
            "insumo_unidad": clean_text_field(item.get("insumo_unidad")),
            
            "rendimiento_insumo": clean_numeric_value(item.get("rendimiento_insumo")),
            "precio_unitario_apu": clean_numeric_value(item.get("precio_unitario_apu")),
            "precio_parcial_apu": clean_numeric_value(item.get("precio_parcial_apu")),
            
            "observacion": clean_text_field(item.get("observacion")),
            "link_documento": filename if filename else clean_text_field(item.get("link_documento"))
        }
        
        for key in ["fecha_aprobacion_apu", "fecha_analisis_apu"]:
            if cleaned[key] == "–":
                cleaned[key] = None

        cleaned_list.append(cleaned)
        
    _classify_tipo_insumo(cleaned_list)
    return cleaned_list


def generate_copy_paste_table(insumos: list, include_proyecto_col: bool = True) -> str:
    """Generates a TSV-like string formatted smoothly for clipboard pasting into Google Sheets."""
    headers = [
        "FECHA DE APROBACIÓN DEL APU", "FECHA DE ANÁLISIS APU", "CIUDAD", "PAÍS", 
        "ENTIDAD", "CONTRATISTA", "NOMBRE DE PROYECTO", "No DE CONTRATO", 
        "ITEM", "ITEMS DESCRIPCIÓN", "ITEM UND.", "PRECIO UNITARIO", 
        "PRECIO UNITARIO SIN AIU", "CÓDIGO INSUMO", "TIPO DE INSUMO", 
        "INSUMO DESCRIPCIÓN", "INSUMO UNIDAD", "RENDIMIENTO INSUMO", 
        "PRECIO UNITARIO APU", "PRECIO PARCIAL APU", "OBSERVACIÓN", "DOCUMENTO"
    ]
    
    if include_proyecto_col:
        headers = ["PROYECTO"] + headers
        
    rows = []
    rows.append("\t".join(headers))
    
    for ins in insumos:
        row_fields = []
        
        if include_proyecto_col:
            row_fields.append(ins.get("link_documento") or ins.get("nombre_proyecto") or "–")
            
        row_fields.extend([
            ins.get("fecha_aprobacion_apu") or "–",
            ins.get("fecha_analisis_apu") or "–",
            ins.get("ciudad") or "–",
            ins.get("pais") or "–",
            ins.get("entidad") or "–",
            ins.get("contratista") or "–",
            ins.get("nombre_proyecto") or "–",
            ins.get("numero_contrato") or "–",
            ins.get("item") or "–",
            ins.get("items_descripcion") or "–",
            ins.get("item_unidad") or "–",
            format_latin_number(ins.get("precio_unitario")),
            format_latin_number(ins.get("precio_unitario_sin_aiu")),
            ins.get("codigo_insumo") or "–",
            ins.get("tipo_insumo") or "–",
            ins.get("insumo_descripcion") or "–",
            ins.get("insumo_unidad") or "–",
            format_latin_number(ins.get("rendimiento_insumo")),
            format_latin_number(ins.get("precio_unitario_apu")),
            format_latin_number(ins.get("precio_parcial_apu")),
            ins.get("observacion") or "–",
            ins.get("link_documento") or "–"
        ])
        
        row_fields = [str(x).strip() if x is not None and str(x).strip() != "" else "–" for x in row_fields]
        rows.append("\t".join(row_fields))
        
    return "\n".join(rows)