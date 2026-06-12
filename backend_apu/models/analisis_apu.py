"""
Análisis APU Models — Compatibility Wrapper
All logic now lives in src/domain/entities/analisis.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.domain.entities.analisis import (
    SolicitudInsumo,
    SolicitudApu,
    AnalisisItem,
    AnalisisApu,
    HistorialAprobacion,
    AnalisisApuCreate,
    AprobarRequest,
    RechazarRequest,
)

__all__ = [
    "SolicitudInsumo", "SolicitudApu", "AnalisisItem", "AnalisisApu",
    "HistorialAprobacion", "AnalisisApuCreate", "AprobarRequest", "RechazarRequest",
]
