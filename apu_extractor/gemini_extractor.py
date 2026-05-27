"""
🧠 AI Extractor Module
Extracts structured APU data from documents using the configured AI provider (Gemini / Ollama).
Cleans and formats data according to user instructions (dates YYYY-MM-DD, Latin numeric format).
"""

import os
import re
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

from apu_extractor.ai_provider import (
    extract_structured,
    extract_from_pdf_multimodal,
)

load_dotenv()

log = logging.getLogger("mapus.extractor")

def clean_numeric_value(value):
    """
    Cleans a potential numeric value extracted from text and returns a float or None.
    Handles currency symbols, dots, commas, etc.
    Auto-detects Latin and US formatting.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
        
    val_str = str(value).strip().replace('$', '').replace('€', '').replace(' ', '')
    if not val_str or val_str in ('–', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return None
        
    try:
        # Check if both dot and comma are present to detect US vs Latin order
        if ',' in val_str and '.' in val_str:
            if val_str.find(',') < val_str.find('.'):
                # Comma comes first: US formatting, e.g. 45,000.50 -> replace commas
                clean_str = val_str.replace(',', '')
            else:
                # Dot comes first: Latin formatting, e.g. 45.000,50 -> remove dots, replace comma
                clean_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            # Only commas: assume decimal comma, e.g. 0,25 or 45000,5
            clean_str = val_str.replace(',', '.')
        else:
            clean_str = val_str
            
        return float(clean_str)
    except ValueError:
        # Fallback if parsing fails
        try:
            return float(val_str)
        except ValueError:
            return None

def format_latin_number(value) -> str:
    """
    Formats a numeric float to Latin format: comma decimal, dot thousands, e.g. 2.846.877,012
    Returns '–' if value is None.
    """
    num = clean_numeric_value(value)
    if num is None:
        return "–"
        
    # Check if it has a decimal part
    if num.is_integer():
        # Format integer: 1234567 -> "1.234.567"
        formatted = f"{int(num):,}".replace(",", ".")
    else:
        # Format float: e.g. 1234567.012 -> "1.234.567,012"
        # First convert to standard string with up to 6 decimal places, removing trailing zeros
        s = f"{num:.6f}".rstrip('0')
        if s.endswith('.'):
            s = s[:-1]
        
        parts = s.split('.')
        int_part = int(parts[0])
        dec_part = parts[1] if len(parts) > 1 else ""
        
        formatted_int = f"{int_part:,}".replace(",", ".")
        if dec_part:
            formatted = f"{formatted_int},{dec_part}"
        else:
            formatted = formatted_int
            
    return formatted

def format_date(value) -> str:
    """
    Cleans and formats date strings into YYYY-MM-DD.
    Returns '–' if invalid.
    """
    if not value:
        return "–"
    val_str = str(value).strip()
    if val_str in ('–', '-', 'NULL', 'null', 'N/A', 'n/a', 'None', ''):
        return "–"
        
    # If already YYYY-MM-DD
    try:
        datetime.strptime(val_str, '%Y-%m-%d')
        return val_str
    except ValueError:
        pass
        
    # Attempt other formats
    formats = ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y', '%Y%m%d']
    for fmt in formats:
        try:
            date_obj = datetime.strptime(val_str, fmt)
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            continue
            
    # Try custom extraction if it contains a year-month-day
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', val_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        
    match_reverse = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', val_str)
    if match_reverse:
        return f"{match_reverse.group(3)}-{int(match_reverse.group(2)):02d}-{int(match_reverse.group(1)):02d}"
        
    return "–"

def clean_text_field(value) -> str:
    """Cleans text fields. Returns '–' if empty."""
    if value is None:
        return "–"
    val_str = str(value).strip()
    if not val_str or val_str in ('–', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return "–"
    return val_str

def get_extraction_prompt(filename: str = None) -> str:
    """
    Returns the comprehensive Prompt Maestro configured for structured JSON output.
    """
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
    - La columna CIUDAD y PAÍS deben deducirse del contexto si no aparecen explícitos (ej. Bogotá, Colombia).
    
    LIMPIEZA DE DATOS (crucial):
    1. IGNORA filas completamente vacías, filas de totales (TOTAL, SUBTOTAL, SUMA), filas de resumen o encabezados repetidos.
    2. IGNORA filas que sean solo separadores (guiones, asteriscos, etc.).
    3. Normaliza descripciones: elimina espacios múltiples, tabs, saltos de línea internos.
    4. Unifica unidades: por ejemplo "H-H", "hh", "HH" → "H-H"; "M3", "mt3" → "M3"; "und", "unidad" → "UND".
    5. Si un insumo no tiene código o descripción clara, no lo incluyas.
    6. Limpia caracteres extraños producto de OCR (corchetes sueltos, símbolos raros, etc.).
    
    RESPONDE EXCLUSIVAMENTE CON UN OBJETO JSON que contenga una lista bajo la clave "insumos".
    Sigue estrictamente la estructura del esquema JSON.
    """

def get_response_schema():
    """
    Returns the JSON schema for Gemini structured output.
    """
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
                        "link_documento": {"type": "STRING", "description": "Dejar vacío o nombre del archivo de origen"}
                    },
                    "required": ["nombre_proyecto", "item", "items_descripcion", "insumo_descripcion"]
                }
            }
        }
    }

def extract_apus_from_text(document_text: str, filename: str = None) -> list:
    """
    Extracts APUs from a text string using the configured AI provider.
    """
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    return extract_structured(prompt, document_text, schema)

def extract_apus_from_pdf_multimodal(pdf_base64: str, filename: str = None) -> list:
    """
    Extracts APUs directly from a base64 encoded PDF using the configured AI provider.
    Falls back to text extraction for providers that don't support multimodal.
    """
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    try:
        return extract_from_pdf_multimodal(pdf_base64, filename, prompt, schema)
    except NotImplementedError:
        log.warning("PDF multimodal not supported by current provider, extracting text first")
        import base64
        import tempfile
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            from apu_extractor.pdf_parser import extract_text_from_pdf
            text = extract_text_from_pdf(tmp_path)
            if text.strip():
                return extract_structured(prompt, text, schema)
            raise
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

def extract_apus_from_excel(excel_path: str, filename: str = None, progress_callback=None) -> list:
    """
    Extracts APUs from an Excel file in batches of rows to avoid exceeding
    the AI context window. Each batch is processed independently and results
    are merged.
    """
    from apu_extractor.excel_parser import extract_text_from_excel_batched

    all_insumos = []
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()

    batches = list(extract_text_from_excel_batched(excel_path))
    total_batches = len(batches)

    for i, (sheet_name, chunk_text) in enumerate(batches):
        log.info("Processing batch %d/%d from %s / %s (%d chars)", i+1, total_batches, filename or excel_path, sheet_name, len(chunk_text))
        if progress_callback:
            progress_callback(i + 1, total_batches, f"Procesando hoja {sheet_name} ({i+1}/{total_batches})")
            
        try:
            batch_result = extract_structured(prompt, chunk_text, schema)
            all_insumos.extend(batch_result)
        except Exception as e:
            log.warning("Batch failed for %s / %s: %s", filename or excel_path, sheet_name, e)

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
        return 0


def extract_apus_from_pdf_batched(pdf_path: str, filename: str = None, progress_callback=None) -> list:
    """
    Extracts APUs from a PDF file in page batches.

    Strategy:
    1. Try multimodal (send PDF page-batches as images) via Gemini
    2. If multimodal fails or not available, fall back to text batches

    Args:
        pdf_path: Path to the PDF file on disk
        filename: Original filename for logging

    Returns:
        Merged list of insumos from all batches
    """
    from apu_extractor.pdf_parser import extract_text_from_pdf_batched

    all_insumos = []
    prompt = get_extraction_prompt(filename)
    schema = get_response_schema()
    total_pages = _get_pdf_page_count(pdf_path)

    use_multimodal = total_pages <= MAX_MULTIMODAL_PAGES

    if use_multimodal:
        from apu_extractor.pdf_parser import split_pdf_to_base64_batches
        try:
            if progress_callback:
                progress_callback(1, 1, "Preparando páginas del PDF para análisis visual...")
                
            multimodal_batches = list(split_pdf_to_base64_batches(pdf_path))
            total = len(multimodal_batches)

            for idx, (label, pdf_b64) in enumerate(multimodal_batches):
                log.info("Multimodal batch %s (%d b64 chars)", label, len(pdf_b64))
                if progress_callback:
                    progress_callback(idx + 1, total, f"IA GEMINI · Analizando imágenes de {label}...")
                try:
                    batch_result = extract_from_pdf_multimodal(pdf_b64, f"{filename} ({label})", prompt, schema)
                    all_insumos.extend(batch_result)
                    log.info("Multimodal batch %s → %d insumos", label, len(batch_result))
                except NotImplementedError:
                    log.info("Multimodal not supported for %s, switching to text", label)
                    use_multimodal = False
                    break
                except Exception as e:
                    log.warning("Multimodal batch %s failed: %s", label, e)
                    # We skip text fallback for individual batch failures to avoid blocking the GIL
                    
            if use_multimodal:
                log.info("Extracted %d insumos from %s (multimodal batched)", len(all_insumos), filename or pdf_path)
                return all_insumos
        except NotImplementedError:
            log.info("Multimodal not available, using text batches")

    total = max(1, (total_pages + 4) // 5)  # 5 is PDF_BATCH_SIZE
    log.info("Using text-based extraction for %s (%d pages, %d batches)", filename or pdf_path, total_pages, total)

    if progress_callback:
        progress_callback(0, total, "Leyendo documento PDF (esto puede tardar unos minutos)...")

    # Evaluate generator lazily so we don't block the thread entirely before any progress
    text_batches_gen = extract_text_from_pdf_batched(pdf_path)
    
    for idx, (label, chunk_text) in enumerate(text_batches_gen):
        log.info("Text batch %s (%d chars)", label, len(chunk_text))
        if progress_callback:
            progress_callback(idx + 1, total, f"IA GEMINI · Procesando texto de {label}...")
            
        try:
            batch_result = extract_structured(prompt, chunk_text, schema)
            all_insumos.extend(batch_result)
            log.info("Text batch %s → %d insumos", label, len(batch_result))
        except Exception as e:
            log.warning("Text batch %s failed: %s", label, e)

    log.info("Extracted %d insumos from %s (text batched)", len(all_insumos), filename or pdf_path)
    return all_insumos



def post_process_extracted_data(insumos: list, filename: str = None) -> list:
    """
    Post-processes and cleans the raw output from Gemini:
    - Standardizes dates to YYYY-MM-DD
    - Cleans numeric columns to pure float or None (for DB)
    - Defaults missing fields to '–'
    - Fills source document link
    """
    cleaned_list = []
    
    for item in insumos:
        # Extract and clean fields
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
        
        # Ensure '–' values are mapped to None for float parameters
        for key in ["precio_unitario", "precio_unitario_sin_aiu", "rendimiento_insumo", "precio_unitario_apu", "precio_parcial_apu"]:
            if cleaned[key] == '–':
                cleaned[key] = None
                
        cleaned_list.append(cleaned)
        
    return cleaned_list

def generate_copy_paste_table(insumos: list, include_proyecto_col: bool = True) -> str:
    """
    Generates a TSV-like string formatted for Google Sheets.
    Converts numbers to Latin formatting: comma decimal, dot thousands, no dollar sign.
    Empty fields represent a dash '–'.
    """
    headers = [
        "FECHA DE APROBACIÓN DEL APU", "FECHA DE ANÁLISIS APU", "CIUDAD", "PAÍS", 
        "ENTIDAD", "CONTRATISTA", "NOMBRE DE PROYECTO", "No DE CONTRATO", 
        "ITEM", "ITEMS DESCRIPCIÓN", "ITEM UND.", "PRECIO UNITARIO", 
        "PRECIO UNITARIO SIN AIU", "CÓDIGO INSUMO", "TIPO DE INSUMO", 
        "INSUMO DESCRIPCIÓN", "INSUMO UNIDAD", "RENDIMIENTO INSUMO", 
        "PRECIO UNITARIO APU", "PRECIO PARCIAL APU"
    ]
    
    if include_proyecto_col:
        headers = ["PROYECTO"] + headers
        
    rows = []
    # Add Header Row
    rows.append("\t".join(headers))
    
    # Add Data Rows
    for ins in insumos:
        row_fields = []
        
        if include_proyecto_col:
            # Source file or project name
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
            format_latin_number(ins.get("precio_parcial_apu"))
        ])
        
        # Replace actual None or empty values in standard fields with '–'
        row_fields = [str(x).strip() if x is not None and str(x).strip() != "" else "–" for x in row_fields]
        rows.append("\t".join(row_fields))
        
    return "\n".join(rows)
