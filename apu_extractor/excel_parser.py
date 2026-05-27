"""
📊 Excel Parser Module
Reads Excel files (.xlsx, .xls) and converts sheets into formatted text/markdown 
chunks efficiently using modern, robust Pandas mapping techniques for safe LLM processing.
"""

import os
import logging
import unicodedata
from typing import Generator, Dict, Tuple, Any
import pandas as pd

log = logging.getLogger("mapus.extractor.excel")

# Parámetros de control de infraestructura y tokens para el LLM
MAX_CHARS_PER_CHUNK = 30_000  # Protege contra token explosion en hojas con demasiadas columnas


def _get_excel_engine(excel_path: str) -> str:
    """
    Selección dinámica del motor de lectura según la extensión del archivo 
    para garantizar soporte nativo tanto de formatos modernos (.xlsx) como antiguos (.xls).
    """
    ext = os.path.splitext(excel_path)[1].lower()
    if ext == ".xlsx":
        return "openpyxl"
    elif ext == ".xls":
        return "xlrd"
    raise ValueError(f"Formato de archivo Excel no soportado en la infraestructura: {ext}")


def _clean_excel_value(val: Any) -> str:
    """
    Formateador especializado de celdas para evitar textos ruidosos 
    como 'nan' o 'Timestamp(...)' en el contexto de la IA.
    """
    if pd.isna(val):
        return ""
        
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
        
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return f"{val:.4f}".rstrip('0').rstrip('.')  # Mantiene hasta 4 decimales limpios
        
    val_str = str(val).strip()
    return unicodedata.normalize("NFKC", val_str)


def excel_to_dataframe_dict(excel_path: str) -> Dict[str, pd.DataFrame]:
    """
    Converts Excel sheets into a dictionary of pandas DataFrames.
    CORRECCIÓN: Fuerza dtype=object para preservar ceros a la izquierda e integridad de códigos de APU.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at: {excel_path}")
        
    try:
        engine = _get_excel_engine(excel_path)
        # dtype=object evita conversiones automáticas destructivas (ej. 00123 -> 123)
        return pd.read_excel(excel_path, sheet_name=None, engine=engine, dtype=object)
    except Exception as e:
        ext = os.path.splitext(excel_path)[1].lower()
        log.error("Failed to read Excel file into DataFrames: %s", e, exc_info=True)
        raise RuntimeError(
            f"No se pudo abrir el Excel ({ext}). "
            f"Verifica dependencias: openpyxl para .xlsx o xlrd para .xls. Error: {e}"
        )


def extract_text_from_excel_batched(excel_path: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> Generator[Tuple[str, str], None, None]:
    """
    Reads an Excel file and yields text chunks vectorially controlled by text size.
    Inyecta encabezados semánticos de APU detectados dinámicamente.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at: {excel_path}")

    try:
        engine = _get_excel_engine(excel_path)
        xl = pd.ExcelFile(excel_path, engine=engine)
    except Exception as e:
        ext = os.path.splitext(excel_path)[1].lower()
        log.error("Failed to open Excel file or missing engines: %s", e, exc_info=True)
        raise RuntimeError(
            f"No se pudo abrir el archivo Excel ({ext}). "
            f"Verifica dependencias: openpyxl para .xlsx o xlrd para .xls. Error: {e}"
        )

    for sheet_name in xl.sheet_names:
        try:
            # Forzamos dtype=object desde el parseo inicial para blindar la consistencia de códigos
            df = xl.parse(sheet_name, header=None, dtype=object)
            df = df.dropna(how='all').dropna(axis=1, how='all')
            if df.empty:
                continue

            # Heurística avanzada para detección de encabezados en APUs de obra
            header_string = ""
            if len(df) > 0:
                header_keywords = {
                    "item", "descripcion", "unidad", "cantidad", 
                    "precio", "codigo", "insumo", "valor", "tarifa"
                }
                
                header_candidates = [
                    str(x).lower().strip() for x in df.iloc[0].tolist() if pd.notna(x)
                ]
                
                header_hits = sum(
                    any(k in cell for k in header_keywords) for cell in header_candidates
                )
                
                if header_hits >= 2:
                    header_row = df.iloc[0].map(_clean_excel_value).tolist()
                    header_string = " | ".join(header_row)
                    df = df.iloc[1:]

            # CORRECCIÓN: Reemplazado .applymap() obsoleto por el mapeo funcional por columnas .apply().
            # Esto silencia advertencias en Pandas 2.1+ y mantiene compatibilidad total con versiones previas.
            df_cleaned = df.apply(lambda col: col.map(_clean_excel_value))
            
            # Vectorización en C de Pandas para unir las columnas por pipes
            rows = df_cleaned.agg(" | ".join, axis=1).tolist()

            current_chunk = []
            current_size = 0
            chunk_index = 1

            for row in rows:
                if len(row) > max_chars:
                    log.warning("Fila monstruo detectada y truncada de %d a %d caracteres", len(row), max_chars)
                    row = row[:max_chars]

                row_size = len(row) + 1
                
                if current_size + row_size > max_chars and current_chunk:
                    meta_header = f"### HOJA: {sheet_name} (Bloque {chunk_index}) ###\n"
                    if header_string:
                        meta_header += f"[ENCABEZADOS]: {header_string}\n"
                        
                    yield sheet_name, meta_header + "\n".join(current_chunk)
                    
                    current_chunk = []
                    current_size = 0
                    chunk_index += 1

                current_chunk.append(row)
                current_size += row_size

            if current_chunk:
                meta_header = f"### HOJA: {sheet_name} (Bloque {chunk_index}) ###\n"
                if header_string:
                    meta_header += f"[ENCABEZADOS]: {header_string}\n"
                yield sheet_name, meta_header + "\n".join(current_chunk)
                
        except Exception as sheet_err:
            log.error("Error processing sheet '%s' in %s: %s", sheet_name, excel_path, sheet_err, exc_info=True)
            continue


def extract_text_from_excel(excel_path: str) -> str:
    """
    Reads an Excel file and converts all sheets into a single consolidated markdown string.
    Reutiliza el generador por lotes para evitar lecturas duplicadas en disco y fugas de RAM.
    """
    sheets_data = {}

    try:
        for sheet_name, text_chunk in extract_text_from_excel_batched(excel_path):
            if sheet_name not in sheets_data:
                sheets_data[sheet_name] = []
            
            clean_lines = [
                line for line in text_chunk.splitlines() 
                if not line.startswith("### HOJA:") and not line.startswith("[ENCABEZADOS]:")
            ]
            sheets_data[sheet_name].extend(clean_lines)

        final_content = []
        for sheet_name, lines in sheets_data.items():
            final_content.append(f"### HOJA COMPLETA: {sheet_name} ###\n" + "\n".join(lines))

        return "\n\n".join(final_content)

    except Exception as e:
        log.exception("Critical exception aggregating text from Excel")
        raise RuntimeError(f"Fallo general en la extracción de texto del Excel: {e}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        log.info("📊 Testing fully vectorized Excel extraction on: %s", test_path)
        try:
            txt = extract_text_from_excel(test_path)
            log.info("✅ Success. Extracted %d characters.", len(txt))
            print("\nPreview of first 600 characters:")
            print("-" * 40)
            print(txt[:600])
            print("-" * 40)
        except Exception as err:
            log.error("Test execution failed: %s", err)
    else:
        print("💡 Usage: python excel_parser.py <path_to_excel>")