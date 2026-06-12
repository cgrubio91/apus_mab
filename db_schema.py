"""
🗄️ Database Schema — Compatibility Wrapper
Re-exports everything from the new Clean Architecture location.
All logic now lives in src/infrastructure/database/schema.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.infrastructure.database.schema import (
    INSUMO_CATEGORIES,
    SCHEMA_STATEMENTS,
    ensure_schema,
)

__all__ = [
    "INSUMO_CATEGORIES",
    "SCHEMA_STATEMENTS",
    "ensure_schema",
]
