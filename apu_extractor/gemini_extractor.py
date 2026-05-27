"""
🧠 AI Extractor Module
Extracts structured APU data from documents using the configured AI provider (Gemini / Ollama).
Cleans, normalizes, and formats data using high-precision Decimal types for construction budgets.
"""

import os
import re
import base64
import tempfile
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Optional, Dict, List
from dotenv import load_dotenv

from apu_extractor.ai_provider import (
    extract_structured,
    extract_from_pdf_multimodal,
)

if os.getenv("ENV", "").lower() != "production":
    load_dotenv()

log = logging.getLogger("mapus.extractor")

# ==========================================================
# DATA SANITIZATION & FORMATTING HELPERS
# ==========================================================

def clean_numeric_value(value: Any) -> Optional[Decimal]:
    """
    Cleans a potential numeric value extracted from text and returns a high-precision Decimal or None.
    Handles currency symbols, architectural dashes, percentages, and selectively fixes OCR confusion characters (O->0, l->1).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
        
    # CORRECCIÓN: Inclusión de remoción de símbolos de porcentaje '%' comunes en AIU/Rendimientos
    val_str = str(value).strip().replace('$', '').replace('€', '').replace('%', '').replace(' ', '').replace(' ', '')
    if not val_str or val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return None
        
    # CORRECCIÓN CRÍTICA: El mapa de OCR solo se gatilla si la cadena tiene apariencia estrictamente numérica.
    # Esto evita corromper palabras válidas como "OBRA" -> "0BRA" o "MANO DE OBRA" -> "MAN0 DE 0BRA".
    if re.match(r'^[\dOoIl.,\-]+$', val_str):
        ocr_map = {'O': '0', 'o': '0', 'l': '1', 'I': '1'}
        for bad, good in ocr_map.items():
            val_str = val_str.replace(bad, good)
        
    try:
        if ',' in val_str and '.' in val_str:
            if val_str.find(',') < val_str.find('.'):
                clean_str = val_str.replace(',', '')
            else:
                clean_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            clean_str = val_str.replace(',', '.')
        elif '.' in val_str:
            if val_str.count('.') > 1:
                clean_str = val_str.replace('.', '')
            else:
                parts = val_str.split('.')
                if len(parts) == 2 and len(parts[1]) == 3 and parts[0].lstrip('-').isdigit():
                    clean_str = val_str.replace('.', '')
                else:
                    clean_str = val_str
        else:
            clean_str = val_str
            
        return Decimal(clean_str)
    except (ValueError, InvalidOperation):
        try:
            return Decimal(val_str)
        except (ValueError, InvalidOperation):
            log.warning("No se pudo parsear el valor numérico de la celda: %s", value)
            return None


def format_latin_number(value: Any) -> str:
    """
    Formats a numeric value into Latin representation (dot thousands, comma decimal) for Google Sheets.
    """
    num = clean_numeric_value(value)
    if num is None:
        return "–"
        
    try:
        if num == num.to_integral_value():
            return f"{int(num):,}".replace(",", ".")
        else:
            s = format(num.normalize(), 'f').rstrip('0')
            
            if not s or s == '-' or s == '-0':
                s = '0'
                
            if s.endswith('.'):
                s = s[:-1]
            
            parts = s.split('.')
            int_part = int(parts[0])
            dec_part = parts[1] if len(parts) > 1 else ""
            
            formatted_int = f"{int_part:,}".replace(",", ".")
            return f"{formatted_int},{dec_part}" if dec_part else formatted_int
    except Exception:
        log.exception("Error de formateo numérico en format_latin_number")
        return "–"


def format_date(value: Any) -> str:
    """Cleans and formats date strings into standardized ISO format YYYY-MM-DD."""
    if not value:
        return "–"
    val_str = str(value).strip()
    if val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None', ''):
        return "–"
        
    try:
        datetime.strptime(val_str, '%Y-%m-%d')
        return val_str
    except ValueError:
        pass
        
    formats = ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y', '%Y%m%d']
    for fmt in formats:
        try:
            date_obj = datetime.strptime(val_str, fmt)
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            continue
            
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', val_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        
    match_reverse = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', val_str)
    if match_reverse:
        return f"{match_reverse.group(3)}-{int(match_reverse.group(2)):02d}-{int(match_reverse.group(1)):02d}"
        
    return "–"


def clean_text_field(value: Any) -> str:
    """Cleans multi-line or whitespace strings in text cells."""
    if value is None:
        return "–"
    val_str = str(value).strip()
    if not val_str or val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return "–"
    return re.sub(r"\s+", " ", val_str)


# ==========================================================
# PROMPTS & SCHEMAS DEFINITIONS
# ==========================================================

def get_extraction_prompt(filename: str = None) -> str:
    """Returns the comprehensive Prompt Maestro configured for structured JSON output."""
    file_info = f" del archivo '{filename}'" if filename else ""
    return f"""
    Actúa como un extractor de datos de alta precisión experto en infraestructura y Análisis de Precios Unitarios (APU).
    Extrae la información relevante de los APUs presentados en el documento{file_info}.
    
    INSTRUCCIONES DE EXTRACCIÓN:
    1. Crea un registro por cada INSUMO del APU (materiales, mano de obra, equipos, transportes, indirectos, etc.).
    2. Cada registro debe representar una fila de insumo asociada a su Ítem correspondiente.
    3. Si existen costos indirectos o AIU, solo inclúyelos si aparecen desagregados como insumos en el APU.
    4. Mapea la información exactamente a los campos definidos en la estructura de salida.
    
    REGLAS DE FORMATO INTERNO:
    - Las fechas deben venir en formato YYYY-MM-DD. Si no se especifican, pon null.
    - Los números (precios, rendimientos, parciales) deben extraerse como números válidos en JSON (floats o enteros). No agregues puntos de miles ni signos de moneda en el JSON; de eso se encargará el formateador de salida del sistema.
    - La columna ENTIDAD corresponde a la entidad contratante (ej. IDU, INVIAS, alcaldías, etc.).
    
    SEGURIDAD CONTRACTUAL (crucial):
    - La columna CIUDAD y PAÍS solo deben completarse si aparecen explícitamente o existe evidencia inequívoca en el documento. No inventes ni asumas información faltante.
    
    LIMPIEZA DE DATOS:
    1. IGNORA filas completamente vacías, filas de totales (TOTAL, SUBTOTAL, SUMA), filas de resumen o encabezados repetidos.
    2. IGNORA filas que sean solo separadores (guiones, asteriscos, etc.).
    3. Normaliza descripciones: elimina espacios múltiples, tabs, saltos de línea internos.
    4. Unifica unidades: por ejemplo "H-H", "hh", "HH" → "H-H"; "M3", "mt3" → "M3"; "und", "unidad" → "UND".
    5. Si un insumo no tiene código o descripción clara, no lo incluyas.
    6. Limpia caracteres extraños producto de OCR (corchetes sueltos, símbolos raros, etc.).
    
    RESPONDE EXCLUSIVAMENTE CON UN OBJETO JSON que contenga una lista bajo la clave "insumos".
    Sigue estrictamente la estructura del esquema JSON.
    """


def get_response_schema() -> Dict[str, Any]:
    """Returns the strict schema mapping for Gemini structured layouts."""
    return {
        "type": "OBJECT",
        "properties": {
            "insumos": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "fecha_aprobacion_apu": {"type": "STRING", "description": "Fecha de aprobación en formato YYYY-MM-DD o null"},
                        "fecha_analisis_apu": {"type": "STRING", "description": "Fecha de análisis en formato YYYY-MM-DD o null"},
                        "ciudad": {"type": "STRING", "description": "Ciudad del proyecto"},
                        "pais": {"type": "STRING", "description": "País del proyecto"},
                        "entidad": {"type": "STRING", "description": "Entidad contratante (ej. IDU)"},
                        "contratista": {"type": "STRING", "description": "Nombre del contratista"},
                        "nombre_proyecto": {"type": "STRING", "description": "Nombre del proyecto de infraestructura"},
                        "numero_contrato": {"type": "STRING", "description": "Número de contrato"},
                        "item": {"type": "STRING", "description": "Código o número de ítem (ej. 1.1, 2.3.a)"},
                        "items_descripcion": {"type": "STRING", "description": "Descripción o nombre del ítem principal"},
                        "item_unidad": {"type": "STRING", "description": "Unidad de medida del ítem (ej. M3, M, KG)"},
                        "precio_unitario": {"type": "NUMBER", "description": "Precio unitario total del ítem con AIU"},
                        "precio_unitario_sin_aiu": {"type": "NUMBER", "description": "Precio unitario del ítem sin AIU"},
                        "codigo_insumo": {"type": "STRING", "description": "Código identificador del insumo"},
                        "tipo_insumo": {"type": "STRING", "description": "Categoría de insumo (Materiales, Mano de Obra, Equipos, Transporte, etc.)"},
                        "insumo_descripcion": {"type": "STRING", "description": "Nombre detallado del insumo"},
                        "insumo_unidad": {"type": "STRING", "description": "Unidad de medida del insumo (ej. H-G, Bto, M3)"},
                        "rendimiento_insumo": {"type": "NUMBER", "description": "Rendimiento del insumo para este ítem"},
                        "precio_unitario_apu": {"type": "NUMBER", "description": "Costo unitario del insumo"},
                        "precio_parcial_apu": {"type": "NUMBER", "description": "Costo parcial calculado (rendimiento * precio unitario)"},
                        "observacion": {"type": "STRING", "description": "Cualquier observación adicional del insumo"},
                        "link_documento": {"type": "STRING", "description": "Nombre del archivo de origen"}
                    },
                    "required": ["item", "items_descripcion", "insumo_descripcion"]
                }
            }
        }
    }


def _normalize_ai_response(result: Any) -> List[Dict[str, Any]]:
    """Normaliza la salida de la IA interceptando estructuras anidadas o arreglos planos directos."""
    if isinstance(result, dict):
        return result.get("insumos", [])
    return result if isinstance(result, list) else []


# ==========================================================
# EXTRACTION METHODS
# ==========================================================

def extract_apus_from_text(document_text: str, filename: str = None) -> List[Dict[str, Any]]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    raw_result = extract_structured(prompt, document_text, schema)
    return _normalize_ai_response(raw_result)


def extract_apus_from_pdf_multimodal(pdf_base64: str, filename: str = None) -> List[Dict[str, Any]]:
    """CORRECCIÓN: Tipado fino list[dict] para optimizar la indexación, autocompletado y linters."""
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    tmp_path = None
    
    try:
        raw_result = extract_from_pdf_multimodal(pdf_base64, filename, prompt, schema)
        return _normalize_ai_response(raw_result)
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
                return _normalize_ai_response(raw_result)
            return []
        except Exception:
            log.exception("Safe extraction text fallback failed")
            raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def extract_apus_from_excel(excel_path: str, filename: str = None, progress_callback=None) -> List[Dict[str, Any]]:
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
            normalized = _normalize_ai_response(batch_result)
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


def extract_apus_from_pdf_batched(pdf_path: str, filename: str = None, progress_callback=None) -> List[Dict[str, Any]]:
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
                    normalized = _normalize_ai_response(batch_result)
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
            normalized = _normalize_ai_response(batch_result)
            all_insumos.extend(normalized)
            log.info("Text batch %s → %d insumos reales", label, len(normalized))
        except Exception as e:
            log.exception("Text batch %s processing failed: %s", label, str(e))

    log.info("Extracted %d insumos from %s (text batched)", len(all_insumos), filename or pdf_path)
    return all_insumos


# ==========================================================
# POST PROCESSING & ETLS
# ==========================================================

def post_process_extracted_data(insumos: list, filename: str = None) -> List[Dict[str, Any]]:
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