"""
🗄️ Database Configuration Module
Centralizes database connection logic for PostgreSQL (Google Cloud SQL)
Uses connection pooling for production-grade performance.
"""

import json
import logging
import os
from datetime import datetime, date
from decimal import Decimal

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2 import pool as pgpool

load_dotenv()

log = logging.getLogger("mapus.db")


class DatabaseConfig:
    """Database configuration singleton"""

    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.port = int(os.getenv("DB_PORT", 5432))
        self.name = os.getenv("DB_NAME")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.sslmode = os.getenv("DB_SSLMODE", "prefer")
        self.cloud_sql_connection_name = os.getenv("CLOUD_SQL_CONNECTION_NAME")
        self.pool_min = int(os.getenv("DB_POOL_MIN", 1))
        self.pool_max = int(os.getenv("DB_POOL_MAX", 10))

    def validate(self):
        """Validate that all required configuration is present"""
        required = {
            "DB_HOST": self.host,
            "DB_NAME": self.name,
            "DB_USER": self.user,
            "DB_PASSWORD": self.password,
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise ValueError(
                f"Missing required database configuration: {', '.join(missing)}\n"
                "Check your .env file."
            )

    def get_connection_params(self):
        """Get connection parameters as a dictionary"""
        if self.cloud_sql_connection_name:
            return {
                "user": self.user,
                "password": self.password,
                "dbname": self.name,
                "host": f"/cloudsql/{self.cloud_sql_connection_name}",
            }
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
            "connect_timeout": 30,
        }


db_config = DatabaseConfig()


class DBEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.strftime("%Y-%m-%d")
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


_connection_pool = None


def _get_pool():
    global _connection_pool
    if _connection_pool is None:
        db_config.validate()
        params = db_config.get_connection_params()
        try:
            _connection_pool = pgpool.ThreadedConnectionPool(
                db_config.pool_min, db_config.pool_max, **params
            )
            log.info(
                "Connection pool created (min=%d, max=%d)",
                db_config.pool_min, db_config.pool_max,
            )
        except Exception as e:
            log.error("Failed to create connection pool: %s", e)
            raise
    return _connection_pool


class PoolConnection:
    """Wrapper that returns the underlying psycopg2 connection to the pool on exit."""

    def __init__(self, conn):
        self.conn = conn

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        put_connection(self.conn)
        return False

    def close(self):
        put_connection(self.conn)


def get_db_connection():
    """Get a connection from the pool, or create one if pool is not available."""
    global _connection_pool
    if _connection_pool is not None:
        try:
            return PoolConnection(_get_pool().getconn())
        except Exception as e:
            log.error("Failed to get connection from pool: %s", e)
            raise

    db_config.validate()
    params = db_config.get_connection_params()
    try:
        conn = psycopg2.connect(**params)
        return conn
    except psycopg2.Error as e:
        log.error("Database connection failed: %s", e)
        raise


def put_connection(conn):
    """Return a connection to the pool, or close it if the pool is not in use."""
    global _connection_pool
    if _connection_pool is not None and conn:
        try:
            _get_pool().putconn(conn)
            return
        except Exception:
            pass
    if conn:
        try:
            conn.close()
        except Exception:
            pass


def execute_query(query, params=None, fetch=True, dict_cursor=True):
    """
    Execute a SQL query with parameterized arguments.
    Returns connections to the pool after use.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)

        cursor.execute(query, params)

        if fetch:
            results = cursor.fetchall()
            cursor.close()
            return results

        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected

    except Exception as e:
        if conn:
            conn.rollback()
        log.error("Query execution failed: %s | Query: %s", e, query[:200])
        raise
    finally:
        put_connection(conn)


def test_connection():
    """Test database connection, return status dict."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        put_connection(conn)
        return {"status": "success", "version": version}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def close_pool():
    """Close all connections in the pool."""
    global _connection_pool
    if _connection_pool is not None:
        _get_pool().closeall()
        _connection_pool = None
        log.info("Connection pool closed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = test_connection()
    if result["status"] == "success":
        log.info("✅ Connection OK — %s", result["version"])
    else:
        log.error("❌ %s", result["message"])
