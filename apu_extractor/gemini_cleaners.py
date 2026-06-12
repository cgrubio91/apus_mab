"""
Gemini Cleaners — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/gemini_cleaners.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.gemini_cleaners import (
    format_latin_number,
    format_date,
    clean_numeric_value,
    clean_text_field,
)

__all__ = ["format_latin_number", "format_date", "clean_numeric_value", "clean_text_field"]
