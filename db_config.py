"""
🗄️ Database Configuration — Compatibility Wrapper
Re-exports everything from the new Clean Architecture location.
All logic now lives in src/infrastructure/database/connection.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.infrastructure.database.connection import (
    DatabaseConfig,
    DBEncoder,
    PoolConnection,
    db_config,
    get_db_connection,
    put_connection,
    execute_query,
    test_connection,
    close_pool,
)

__all__ = [
    "DatabaseConfig",
    "DBEncoder",
    "PoolConnection",
    "db_config",
    "get_db_connection",
    "put_connection",
    "execute_query",
    "test_connection",
    "close_pool",
]
