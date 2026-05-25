"""
🧠 Gemini Extractor Module
Communicates with Google Gemini API to extract structured APU data from documents.
Cleans and formats data according to user instructions (dates YYYY-MM-DD, Latin numeric format).
"""

import os
import re
import json
import requests
from datetime import datetime

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

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

def call_gemini_api(contents_payload: list) -> list:
    """
    Helper function to send content to the Gemini API and request JSON output.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": contents_payload,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": get_response_schema(),
            "temperature": 0.1
        }
    }
    
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        if "candidates" not in data or not data["candidates"]:
            raise Exception(f"No response candidates returned from Gemini: {json.dumps(data)}")
            
        content_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        parsed_json = json.loads(content_text)
        return parsed_json.get("insumos", [])
        
    except Exception as e:
        raise Exception(f"Error communicating with Gemini API: {e}")

def extract_apus_from_text(document_text: str, filename: str = None) -> list:
    """
    Extracts APUs from a text string (such as parsed Excel or PDF text).
    """
    prompt = get_extraction_prompt(filename)
    
    contents_payload = [
        {
            "parts": [
                {"text": prompt},
                {"text": f"Aquí está el contenido del documento:\n\n{document_text}"}
            ]
        }
    ]
    
    return call_gemini_api(contents_payload)

def extract_apus_from_pdf_multimodal(pdf_base64: str, filename: str = None) -> list:
    """
    Extracts APUs directly from a base64 encoded PDF file using Gemini's native PDF support.
    This provides maximum accuracy for complex layouts.
    """
    prompt = get_extraction_prompt(filename)
    
    contents_payload = [
        {
            "parts": [
                {"text": prompt},
                {
                    "inlineData": {
                        "mimeType": "application/pdf",
                        "data": pdf_base64
                    }
                }
            ]
        }
    ]
    
    return call_gemini_api(contents_payload)

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
