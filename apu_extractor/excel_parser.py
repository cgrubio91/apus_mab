"""
Excel Parser — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/excel_parser.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.excel_parser import (
    extract_text_from_excel,
    excel_to_dataframe_dict,
    extract_text_from_excel_batched,
)

__all__ = ["extract_text_from_excel", "excel_to_dataframe_dict", "extract_text_from_excel_batched"]
