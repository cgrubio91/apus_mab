"""
Infrastructure: indexación temporal de precios (pesos constantes).

Ajusta un precio nominal de una fecha a otra usando una serie de índices de
costos (ej. DANE ICCP para obra civil, o IPC). Puro y testeable; la carga de la
serie (tabla indice_costos / API DANE) es responsabilidad de otra capa.

Un precio de hace dos años no es comparable a hoy: este módulo lo lleva a la
fecha objetivo antes de compararlo contra una cotización actual.
"""

from datetime import date, datetime
from typing import Optional


def _periodo(fecha) -> Optional[str]:
    """'YYYY-MM' de una fecha (str/date/datetime)."""
    if fecha is None:
        return None
    if isinstance(fecha, (date, datetime)):
        return fecha.strftime("%Y-%m")
    s = str(fecha)
    return s[:7] if len(s) >= 7 else None


def indice_para_periodo(serie: dict, periodo: Optional[str]) -> Optional[float]:
    """Índice del periodo exacto o, si no existe, el del último periodo anterior
    disponible (los índices se publican mensualmente y a veces con rezago)."""
    if not serie or not periodo:
        return None
    if periodo in serie:
        try:
            return float(serie[periodo])
        except (TypeError, ValueError):
            return None
    anteriores = sorted(p for p in serie if p <= periodo)
    if not anteriores:
        return None
    try:
        return float(serie[anteriores[-1]])
    except (TypeError, ValueError):
        return None


def ajustar_precio(precio, fecha_origen, fecha_destino, serie: dict) -> Optional[float]:
    """Lleva `precio` de `fecha_origen` a `fecha_destino` con la serie de índices.

    Devuelve el precio ajustado, o el precio sin cambio si falta información para
    indexar (no inventa: si no hay índice, no ajusta).
    """
    try:
        p = float(precio)
    except (TypeError, ValueError):
        return None
    i_origen = indice_para_periodo(serie, _periodo(fecha_origen))
    i_destino = indice_para_periodo(serie, _periodo(fecha_destino))
    if not i_origen or not i_destino or i_origen == 0:
        return round(p, 6)
    return round(p * i_destino / i_origen, 6)
