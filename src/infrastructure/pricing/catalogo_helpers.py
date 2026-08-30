"""
Infrastructure: helpers puros del catálogo de insumos y del histórico de precios.

Sin BD ni IA: firma canónica para deduplicar insumos, normalización de
descripción para sinónimos y estadísticas de precio con ponderación por recencia.
Se prueban en unidad.
"""

from datetime import date, datetime
from typing import Optional

from src.infrastructure.database.repositories.analisis_repository import (
    _normalizar,
    _tokenizar,
)


def descripcion_normalizada(descripcion: str) -> str:
    """Forma normalizada (minúsculas, sin tildes, espacios colapsados) que sirve
    de clave de sinónimo: dos descripciones que solo difieren en mayúsculas,
    tildes o espacios comparten sinónimo."""
    return " ".join(_normalizar(descripcion).split())


def firma_insumo(descripcion: str) -> str:
    """Firma canónica de un insumo: tokens significativos ordenados. Insumos que
    comparten el mismo conjunto de palabras clave ('cemento gris' == 'gris cemento')
    se colapsan al mismo maestro. Cadena vacía si no hay tokens útiles."""
    tokens = _tokenizar(descripcion)
    return " ".join(sorted(tokens))


def mediana(valores: list) -> Optional[float]:
    vals = sorted(float(v) for v in valores if v is not None)
    if not vals:
        return None
    n = len(vals)
    m = n // 2
    if n % 2:
        return float(vals[m])
    return round((vals[m - 1] + vals[m]) / 2, 6)


def _a_fecha(valor) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def estadisticas_precio(observaciones: list[dict]) -> dict:
    """Resume una lista de observaciones de precio de un insumo.

    Cada observación: {"precio": float, "fecha": date|str|None}.
    Devuelve n, mediana, min, max, y el precio MÁS RECIENTE con su fecha
    (el dato preferido para cotizar hoy).
    """
    precios = []
    reciente_val = None
    reciente_fecha: Optional[date] = None
    for o in observaciones or []:
        try:
            p = float(o.get("precio"))
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        precios.append(p)
        f = _a_fecha(o.get("fecha"))
        # El más reciente: fecha mayor; una fecha real gana a "sin fecha".
        if reciente_fecha is None and reciente_val is None:
            reciente_val, reciente_fecha = p, f
        elif f is not None and (reciente_fecha is None or f > reciente_fecha):
            reciente_val, reciente_fecha = p, f
    if not precios:
        return {"n": 0, "mediana": None, "min": None, "max": None,
                "precio_reciente": None, "fecha_reciente": None}
    return {
        "n": len(precios),
        "mediana": mediana(precios),
        "min": round(min(precios), 6),
        "max": round(max(precios), 6),
        "precio_reciente": round(reciente_val, 6) if reciente_val is not None else None,
        "fecha_reciente": reciente_fecha.isoformat() if reciente_fecha else None,
    }
