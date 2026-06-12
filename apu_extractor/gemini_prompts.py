"""
Gemini Prompts — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/gemini_prompts.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.gemini_prompts import (
    get_extraction_prompt,
    get_response_schema,
)

__all__ = ["get_extraction_prompt", "get_response_schema"]
