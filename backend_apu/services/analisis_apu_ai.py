"""
Análisis APU AI — Compatibility Wrapper
All logic now lives in src/application/use_cases/manage_analisis.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.application.use_cases.manage_analisis import (
    _analisis_con_ia as analisis_con_ia,
    _generar_resumen_ia as generar_resumen_ia,
)

__all__ = ["analisis_con_ia", "generar_resumen_ia"]
