"""
Infrastructure: Fuente DANE — series de índices de costos de construcción

Trae una serie de índices (ej. ICCP — Índice de Costos de la Construcción Pesada,
o IPC) desde un dataset Socrata de datos.gov.co y la normaliza a puntos
(periodo 'YYYY-MM', valor) para la tabla indice_costos.

El mapeo (`mapear_fila_indice`) es PURO y tolerante a nombres de columna (los
datasets DANE varían: 'periodo'/'mes'/'fecha' y 'indice'/'valor'/'numero_indice').
"""

import logging
import re
from typing import Optional

from src.infrastructure.scraping.socrata_client import SocrataClient

log = logging.getLogger("mapus.infrastructure.dane")

FUENTE = "DANE"

_CAMPOS_PERIODO = ["periodo", "mes", "fecha", "anio_mes", "ano_mes", "vigencia"]
_CAMPOS_VALOR = ["indice", "valor", "numero_indice", "numero_de_indice", "indice_total", "total"]

_MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05",
    "junio": "06", "julio": "07", "agosto": "08", "septiembre": "09", "setiembre": "09",
    "octubre": "10", "noviembre": "11", "diciembre": "12",
}


def _primero(row: dict, claves: list[str]) -> Optional[str]:
    for k in claves:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def normalizar_periodo(valor: str, anio: Optional[str] = None) -> Optional[str]:
    """Lleva distintos formatos de periodo a 'YYYY-MM'.
    Acepta '2025-06', '2025-06-01', '202506', 'junio 2025', 'junio' (+ anio)."""
    if not valor:
        return None
    s = str(valor).strip().lower()
    m = re.match(r"^(\d{4})[-/]?(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    for nombre, num in _MESES.items():
        if nombre in s:
            m2 = re.search(r"(\d{4})", s)
            year = m2.group(1) if m2 else anio
            if year:
                return f"{year}-{num}"
    if re.match(r"^\d{4}$", s) and anio is None:
        return None  # solo año, sin mes → no sirve para una serie mensual
    return None


def _parse_valor(valor) -> Optional[float]:
    if valor is None:
        return None
    s = re.sub(r"[^\d.,-]", "", str(valor))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def mapear_fila_indice(row: dict, campo_periodo: Optional[str] = None,
                       campo_valor: Optional[str] = None) -> Optional[tuple]:
    """Convierte una fila cruda en (periodo 'YYYY-MM', valor) o None."""
    periodo_raw = row.get(campo_periodo) if campo_periodo else _primero(row, _CAMPOS_PERIODO)
    valor_raw = row.get(campo_valor) if campo_valor else _primero(row, _CAMPOS_VALOR)
    anio = _primero(row, ["anio", "ano", "year"])
    periodo = normalizar_periodo(periodo_raw, anio=anio)
    valor = _parse_valor(valor_raw)
    if not periodo or valor is None:
        return None
    return (periodo, valor)


class DaneSource:
    def __init__(self, client: Optional[SocrataClient] = None):
        self.client = client or SocrataClient()

    def obtener_serie(self, dataset_id: str, campo_periodo: Optional[str] = None,
                      campo_valor: Optional[str] = None, where: Optional[str] = None,
                      max_total: int = 5000) -> list[tuple]:
        """Descarga y normaliza una serie completa (paginando)."""
        params = {"$order": ":id"}
        if where:
            params["$where"] = where
        filas = self.client.query_paginado(dataset_id, params, max_total=max_total)
        puntos = {}
        for row in filas:
            p = mapear_fila_indice(row, campo_periodo, campo_valor)
            if p:
                puntos[p[0]] = p[1]  # último valor por periodo gana
        salida = sorted(puntos.items())
        log.info("DANE: %d fila(s) → %d punto(s) de serie", len(filas), len(salida))
        return salida
