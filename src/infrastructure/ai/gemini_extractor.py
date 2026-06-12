"""
Infrastructure: Gemini-based APU Extractor
Core extraction orchestration: PDF (multimodal + text) and Excel pipelines.
"""

import copy
import logging
import re
from typing import Optional

from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.ai.pdf_parser import (
    extract_text_from_pdf,
    split_pdf_to_base64_batches,
)
from src.infrastructure.ai.excel_parser import (
    extract_text_from_excel,
    extract_text_from_excel_batched,
)
from src.infrastructure.ai.gemini_prompts import (
    get_extraction_prompt,
    get_response_schema,
)
from src.infrastructure.ai.gemini_cleaners import (
    format_latin_number,
    format_date,
    clean_text_field,
    clean_numeric_value,
)

log = logging.getLogger("mapus.extractor.gemini")

MAX_CHARS_PER_BATCH = 80000


def extract_apus_from_text(pdf_text: str, filename: str, progress_callback=None) -> list:
    prompt = get_extraction_prompt()
    schema = get_response_schema()
    return ai_provider.extract_structured(prompt, pdf_text, schema)


def extract_apus_from_pdf_multimodal(pdf_path: str, filename: str, progress_callback=None) -> list:
    from src.infrastructure.ai.pdf_parser import get_pdf_base64
    pdf_base64 = get_pdf_base64(pdf_path)
    prompt = get_extraction_prompt()
    schema = get_response_schema()
    return ai_provider.extract_from_pdf_multimodal(pdf_base64, filename, prompt, schema)


def extract_apus_from_pdf_batched(pdf_path: str, filename: str, progress_callback=None) -> list:
    all_insumos = []
    batches = split_pdf_to_base64_batches(pdf_path, batch_size=15)
    total_batches = len(batches)

    for i, batch in enumerate(batches):
        if progress_callback:
            progress_callback(i, total_batches, f"Extrayendo lote {i + 1}/{total_batches} (págs. {batch['pages']})")

        try:
            insumos = ai_provider.extract_from_pdf_multimodal(
                batch["base64"], f"{filename} (págs. {batch['pages']})",
                get_extraction_prompt(), get_response_schema(),
                timeout=600,
            )
            if insumos:
                all_insumos.extend(insumos)
                log.info("Lote %d/%d: %d insumos extraídos", i + 1, total_batches, len(insumos))
        except Exception as e:
            log.warning("Lote %d/%d falló con multimodal, reintentando con texto...", i + 1, total_batches)
            try:
                text = batch.get("text", "")
                if len(text) > MAX_CHARS_PER_BATCH:
                    text = text[:MAX_CHARS_PER_BATCH]
                insumos = ai_provider.extract_structured(
                    get_extraction_prompt(), text, get_response_schema(), timeout=300,
                )
                if insumos:
                    all_insumos.extend(insumos)
                    log.info("Lote %d/%d (texto): %d insumos extraídos", i + 1, total_batches, len(insumos))
            except Exception as e2:
                log.error("Lote %d/%d falló completamente: %s", i + 1, total_batches, e2)

    log.info("Extracción completada: %d insumos en %d lotes", len(all_insumos), total_batches)
    return all_insumos


def extract_apus_from_excel(excel_path: str, filename: str, progress_callback=None) -> list:
    all_insumos = []
    batches = extract_text_from_excel_batched(excel_path, max_chars=MAX_CHARS_PER_BATCH)
    total_batches = len(batches)

    for i, batch_text in enumerate(batches):
        if progress_callback:
            progress_callback(i, total_batches, f"Extrayendo lote {i + 1}/{total_batches}")

        try:
            insumos = ai_provider.extract_structured(
                get_extraction_prompt(), batch_text, get_response_schema(), timeout=300,
            )
            if insumos:
                all_insumos.extend(insumos)
                log.info("Excel lote %d/%d: %d insumos", i + 1, total_batches, len(insumos))
        except Exception as e:
            log.error("Excel lote %d/%d falló: %s", i + 1, total_batches, e)

    return all_insumos


def post_process_extracted_data(raw_data: list, filename: str) -> list:
    cleaned = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue

        processed = {
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
            "link_documento": filename,
        }

        has_data = any(v is not None and v != "" for v in processed.values())
        if has_data:
            cleaned.append(processed)

    return cleaned


def generate_copy_paste_table(data: list) -> str:
    if not data:
        return "No hay datos para exportar."

    headers = [
        "nombre_proyecto", "item", "items_descripcion", "item_unidad",
        "precio_unitario", "codigo_insumo", "insumo_descripcion",
        "insumo_unidad", "rendimiento_insumo", "precio_unitario_apu",
        "precio_parcial_apu", "tipo_insumo",
    ]

    lines = ["\t".join(headers)]
    for row in data:
        line = "\t".join(str(row.get(h, "")) or "" for h in headers)
        lines.append(line)

    return "\n".join(lines)
