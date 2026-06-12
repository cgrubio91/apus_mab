"""
SQL Validator — Compatibility Wrapper
All logic now lives in src/infrastructure/sql_validator.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.sql_validator import (
    validate_readonly_query,
    ALLOWED_TABLES,
    ALLOWED_COLUMNS,
    MAX_LIMIT,
)

__all__ = ["validate_readonly_query", "ALLOWED_TABLES", "ALLOWED_COLUMNS", "MAX_LIMIT"]
