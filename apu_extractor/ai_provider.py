"""
🤖 AI Provider — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/provider.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.provider import ai_provider

generate_text = ai_provider.generate_text
extract_structured = ai_provider.extract_structured
extract_from_pdf_multimodal = ai_provider.extract_from_pdf_multimodal

__all__ = ["generate_text", "extract_structured", "extract_from_pdf_multimodal"]
