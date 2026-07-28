"""
Infrastructure: Excel Parser
Extrae texto de archivos Excel para consumo de la IA.

Los APU vienen en plantillas (INVIAS/MEPI) con secciones (I. EQUIPO, II. MATERIALES,
III. TRANSPORTES, IV. MANO DE OBRA), sub-encabezados y celdas combinadas. Renderizar
con `pandas.to_string` desalinea los valores (columnas "Unnamed" y cientos de espacios
de relleno) y la IA pierde los rendimientos/precios. Aquí se produce una grilla compacta
fila-a-fila con openpyxl para que cada valor quede junto a su etiqueta.
"""

import logging

import openpyxl

log = logging.getLogger("mapus.extractor.excel")


def _fmt_celda(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        # Enteros como enteros; decimales sin ceros sobrantes.
        return str(int(v)) if v.is_integer() else f"{v:g}"
    return str(v).strip()


def extract_text_from_excel(excel_path: str) -> str:
    """Renderiza el libro como grillas compactas: una línea por fila con celdas
    separadas por ' | ', recortando columnas vacías al final. Preserva la posición
    de cada valor respecto a su etiqueta sin el relleno de `to_string`."""
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    fragmentos = []
    try:
        for ws in wb.worksheets:
            fragmentos.append(f"=== Hoja: {ws.title} ===")
            for fila in ws.iter_rows(values_only=True):
                celdas = [_fmt_celda(c) for c in fila]
                while celdas and celdas[-1] == "":
                    celdas.pop()
                if not any(celdas):
                    continue
                fragmentos.append(" | ".join(celdas))
    finally:
        wb.close()
    return "\n".join(fragmentos)


def extract_text_from_excel_batched(excel_path: str, max_chars: int = 50000) -> list[str]:
    """Parte el texto en lotes por líneas completas (sin cortar filas a la mitad)."""
    text = extract_text_from_excel(excel_path)
    lineas = text.split("\n")
    batches: list[str] = []
    actual: list[str] = []
    largo = 0
    for ln in lineas:
        if largo + len(ln) + 1 > max_chars and actual:
            batches.append("\n".join(actual))
            actual, largo = [], 0
        actual.append(ln)
        largo += len(ln) + 1
    if actual:
        batches.append("\n".join(actual))
    return batches if batches else [text]
