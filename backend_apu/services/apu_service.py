"""
APU Service — Compatibility Wrapper
All logic now lives in src/infrastructure/database/repositories/apu_repository.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.infrastructure.database.repositories.apu_repository import (
    ApuPostgresRepository as ApuService,
    apu_repo as apu_service,
)

__all__ = ["ApuService", "apu_service"]
