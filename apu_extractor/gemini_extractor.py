"""
Gemini Extractor — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/gemini_extractor.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.gemini_extractor import (
    extract_apus_from_text,
    extract_apus_from_pdf_multimodal,
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
)

__all__ = [
    "extract_apus_from_text", "extract_apus_from_pdf_multimodal",
    "extract_apus_from_excel", "extract_apus_from_pdf_batched",
    "post_process_extracted_data", "generate_copy_paste_table",
]
