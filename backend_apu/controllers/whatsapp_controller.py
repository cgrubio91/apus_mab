"""
WhatsApp Controller — Compatibility Wrapper
All logic now lives in src/presentation/routers/whatsapp.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.presentation.routers.whatsapp import router

__all__ = ["router"]
