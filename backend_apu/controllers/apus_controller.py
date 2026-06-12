"""
APUs Controller — Compatibility Wrapper
All logic now lives in src/presentation/routers/apus.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.presentation.routers.apus import router

__all__ = ["router"]
