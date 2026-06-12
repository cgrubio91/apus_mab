"""
APU Models — Compatibility Wrapper
All logic now lives in src/domain/entities/apu.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.domain.entities.apu import ApuRecord, ApuFilters, ApuListResponse

__all__ = ["ApuRecord", "ApuFilters", "ApuListResponse"]
