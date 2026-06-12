"""
Análisis APU Service — Compatibility Wrapper
All logic now lives in src/application/use_cases/manage_analisis.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.infrastructure.database.repositories.analisis_repository import (
    AnalisisPostgresRepository as AnalisisApuService,
    analisis_repo as analisis_apu_service,
)

__all__ = ["AnalisisApuService", "analisis_apu_service"]
