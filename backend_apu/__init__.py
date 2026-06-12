"""
Backend APU Module — Compatibility Wrapper
All logic now lives in src/
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.presentation.main import create_app
from src.domain.entities.apu import ApuRecord
from src.infrastructure.database.repositories.apu_repository import ApuPostgresRepository as ApuService

__all__ = ["create_app", "ApuRecord", "ApuService"]
