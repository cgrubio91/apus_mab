"""
PDF Parser — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/pdf_parser.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.pdf_parser import (
    extract_text_from_pdf,
    get_pdf_base64,
    split_pdf_to_base64_batches,
    extract_text_from_pdf_batched,
)

__all__ = ["extract_text_from_pdf", "get_pdf_base64", "split_pdf_to_base64_batches", "extract_text_from_pdf_batched"]
