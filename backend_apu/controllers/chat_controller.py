"""
Chat Controller — Compatibility Wrapper
All logic now lives in src/presentation/routers/chat.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.presentation.routers.chat import router

__all__ = ["router"]
