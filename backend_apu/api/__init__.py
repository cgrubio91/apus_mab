"""
Backend APU API Router — Compatibility Wrapper
All logic now lives in src/presentation/routers/__init__.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.presentation.routers import api_router

__all__ = ["api_router"]
